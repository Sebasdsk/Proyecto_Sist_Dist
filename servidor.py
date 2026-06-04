import socket
import threading
import time
import json

# ============================================================
# CONFIGURACION DE PUERTOS
# ============================================================
HOST = ''               # '' significa escuchar en todas las interfaces de red
UDP_PORT = 5000         # Puerto para descubrimiento (broadcast UDP)
TCP_PORT = 5001         # Puerto para comunicacion con clientes (TCP)
REPLICA_PORT = 5002     # Puerto para comunicarse con el servidor replica (TCP)

# ============================================================
# VARIABLES GLOBALES
# ============================================================
clients = []            # Lista de clientes conectados {'sock': socket, 'username': str, 'addr': tuple}
clients_lock = threading.Lock()  # Candado para proteger la lista de clientes (hilos seguros)

replica_active = False              # Indica si la replica esta activa
replica_last_heartbeat = 0          # Momento del ultimo heartbeat exitoso

MAX_HISTORY = 50   # Cantidad maxima de mensajes a recordar

# Lista en memoria con el historial de mensajes (los mas recientes al final)
history = []

# Funcion auxiliar para obtener la IP de red real
# (no 127.0.0.1 que es localhost)
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


# Funcion auxiliar para enviar historial a un cliente nuevo
def send_history_to_client(sock):
    # Tomar los ultimos MAX_HISTORY mensajes
    recent = history[-MAX_HISTORY:]
    for msg in recent:
        try:
            data = json.dumps({'type': 'history', 'content': msg}) + '\n'
            sock.sendall(data.encode())
        except:
            break

# ============================================================
# DESCRIPCION GENERAL DEL PROTOCOLO
# ============================================================
# 1. Los clientes descubren el servidor mediante broadcast UDP al puerto 5000
# 2. El servidor responde con su direccion IP y el puerto TCP (5001)
# 3. Los clientes se conectan via TCP al puerto 5001
# 4. El servidor distribuye mensajes a todos los clientes conectados
# 5. El servidor envia copia de cada mensaje a la replica
# 6. El servidor verifica periodicamente si la replica responde (heartbeat)

# ============================================================
# FUNCION: handle_udp_discovery
# ============================================================
# PURPOSE: Escuchar broadcast UDP y responder con la direccion del servidor
# FLOW:    Cliente ----(broadcast)----> Servidor ----(respuesta)----> Cliente
# ============================================================
def handle_udp_discovery():
    # Crear socket UDP (no orientado a conexion)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # SO_REUSEADDR permite reusar el puerto inmediatamente despues de cerrar
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Vincular socket al puerto 5000 en todas las interfaces
    # '' significa 0.0.0.0 (todas las interfaces de red del equipo)
    sock.bind(('', UDP_PORT))

    # Timeout de 1 segundo para poder verificar periodicamente otras cosas
    sock.settimeout(1.0)
    print(f"[UDP] Discovery escuchando en puerto {UDP_PORT}")

    # Bucle infinito - el servidor siempre esta escuchando descubrimientos
    while True:
        try:
            # Recibir datos del cliente (bloquea hasta que llegue algo o timeout)
            # data = contenido del mensaje
            # addr = tupla (ip_remota, puerto_remoto)
            data, addr = sock.recvfrom(1024)

            # Verificar si el cliente pide descubrir el servidor
            if data == b"DISCOVER_SERVER":
                # Obtener la IP del equipo donde corre el servidor
                # Usamos get_local_ip() que devuelve la IP de red real
                # (no 127.0.0.1 que es localhost)
                ip_local = get_local_ip()

                # Construir respuesta: "IP_SERVIDOR:PUERTO_TCP"
                response = f"{ip_local}:{TCP_PORT}"

                # Enviar respuesta directamente al cliente que pidio
                # addr contiene la direccion del cliente solicitante
                sock.sendto(response.encode(), addr)
                print(f"[UDP] Respuesta enviada a {addr}: {response}")

        except socket.timeout:
            # No hubo datos en 1 segundo, continuar el bucle
            continue

# ============================================================
# FUNCION: handle_tcp_clients
# ============================================================
# PURPOSE: Aceptar conexiones TCP de clientes y crear un hilo para cada uno
# FLOW:    main() --accept()--> handle_client() --recv/send--> Cliente
# ============================================================
def handle_tcp_clients():
    # Crear socket TCP (orientado a conexion)
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Permitir reusar el puerto
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Vincular a todas las interfaces, puerto 5001
    server_sock.bind(('0.0.0.0', TCP_PORT))

    # Empezar a escuchar, backlog de 5 (maximo de conexiones pendientes)
    server_sock.listen(5)
    print(f"[TCP] Servidor Chat escuchando en puerto {TCP_PORT}")

    # Bucle infinito - siempre aceptando nuevos clientes
    while True:
        # Aceptar conexion entrante (bloquea hasta que llegue alguien)
        # client_sock = nuevo socket para comunicarse con este cliente
        # addr = direccion del cliente (ip, puerto)
        client_sock, addr = server_sock.accept()
        print(f"[TCP] Cliente conectado desde {addr}")

        # Crear un hilo dedicado para manejar a este cliente
        # handle_client() recibira el socket y la direccion
        # daemon=True significa que el hilo termina cuando el programa principal termina
        thread = threading.Thread(target=handle_client, args=(client_sock, addr))
        thread.daemon = True
        thread.start()

# ============================================================
# FUNCION: handle_client
# ============================================================
# PURPOSE: Procesar mensajes de un cliente especifico
# FLOW:    recv() --> parsear JSON --> broadcast a todos --> guardar --> enviar a replica
# ============================================================
def handle_client(client_sock, addr):
    username = None  # Nombre del usuario (se asigna al hacer login)
    buffer = ""      # Buffer para guardar datos incompletos de la red

    try:
        # Bucle infinito - leer mensajes mientras el cliente este conectado
        while True:
            # Recibir datos del cliente (maximo 4096 bytes)
            data = client_sock.recv(4096)

            # Si data esta vacio, el cliente cerro la conexion
            if not data:
                break

            # Agregar datos recibidos al buffer
            # Los datos pueden llegar en partes, por eso usamos buffer
            buffer += data.decode()

            # Procesar todos los mensajes completos en el buffer
            # Un mensaje completo termina con '\n' (newline)
            while '\n' in buffer:
                # Separar el primer mensaje completo del buffer
                # split('\n', 1) divide solo en el primer '\n'
                line, buffer = buffer.split('\n', 1)

                try:
                    # Convertir JSON string a objeto Python
                    message = json.loads(line)

                    # ============================================================
                    # TIPO DE MENSAJE: LOGIN
                    # ============================================================
                    if message['type'] == 'login':
                        # El cliente envia su nombre de usuario
                        username = message['username']

                        # Agregar cliente a la lista (protegido por candado)
                        with clients_lock:
                            clients.append({
                                'sock': client_sock,
                                'username': username,
                                'addr': addr
                            })

                        print(f"[CHAT] {username} se ha conectado")

                        # Enviar historial de mensajes al nuevo cliente
                        send_history_to_client(client_sock)

                        # Notificar a todos los clientes que alguien nuevo entro
                        broadcast(json.dumps({
                            'type': 'system',
                            'content': f'{username} se ha conectado'
                        }))

                    # ============================================================
                    # TIPO DE MENSAJE: MESSAGE
                    # ============================================================
                    elif message['type'] == 'message' and username:
                        # Construir mensaje completo: "Juan: Hola mundo"
                        full_message = f"{username}: {message['content']}"
                        print(f"[CHAT] {full_message}")

                        # Enviar mensaje a TODOS los clientes conectados
                        broadcast(json.dumps({
                            'type': 'message',
                            'content': full_message
                        }))

                        # Guardar en archivo historial.txt
                        save_to_history(full_message)

                        # Enviar copia a la replica para respaldo
                        send_to_replica(full_message)

                except json.JSONDecodeError:
                    # El JSON esta incompleto o mal formateado, ignorar
                    continue

    except Exception as e:
        print(f"[ERROR] Cliente {addr}: {e}")

    finally:
        # ============================================================
        # LIMPIEZA AL DESCONECTARSE
        # ============================================================
        if username:
            # Remover cliente de la lista
            with clients_lock:
                clients[:] = [c for c in clients if c['sock'] != client_sock]

            # Notificar a todos que el usuario se fue
            broadcast(json.dumps({
                'type': 'system',
                'content': f'{username} se ha desconectado'
            }))
            print(f"[CHAT] {username} se ha desconectado")

        # Cerrar socket del cliente
        client_sock.close()

# ============================================================
# FUNCION: broadcast
# ============================================================
# PURPOSE: Enviar un mensaje a TODOS los clientes conectados
# ============================================================
def broadcast(message):
    with clients_lock:
        disconnected = []

        # Iterar sobre todos los clientes
        for client in clients:
            try:
                # Enviar mensaje con formato: JSON + newline
                # El newline sirve como delimitador para el receptor
                client['sock'].sendall((message + '\n').encode())
            except:
                # Si falla el envio, marcar para desconectar
                disconnected.append(client)

        # Remover clientes que se desconectaron
        for c in disconnected:
            clients.remove(c)

# ============================================================
# FUNCION: save_to_history
# ============================================================
# PURPOSE: Guardar mensaje en archivo historial.txt y en memoria
# ============================================================
def save_to_history(msg):
    global history

    # Agregar timestamp al mensaje
    timestamp = time.strftime('%H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"

    # Guardar en memoria
    history.append(full_msg)

    # Limitar tamano de la lista en memoria
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    # Guardar en archivo para persistencia
    with open('historial.txt', 'a') as f:
        f.write(f"{full_msg}\n")

# ============================================================
# FUNCION: send_to_replica
# ============================================================
# PURPOSE: Enviar mensaje al servidor replica para respaldo
# ============================================================
def send_to_replica(msg):
    global replica_active, replica_last_heartbeat

    try:
        # Crear conexion TCP con la replica
        replica_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        replica_sock.settimeout(3)  # Timeout de 3 segundos
        replica_sock.connect(('localhost', REPLICA_PORT))

        # Enviar mensaje JSON
        replica_sock.sendall(json.dumps({
            'type': 'message',
            'content': msg
        }).encode())

        replica_sock.close()

        # Marcar replica como activa y guardar timestamp
        replica_active = True
        replica_last_heartbeat = time.time()

    except Exception as e:
        print(f"[REPLICA] Error al enviar mensaje: {e}")
        replica_active = False

# ============================================================
# FUNCION: heartbeat_check
# ============================================================
# PURPOSE: Verificar periodicamente si la replica sigue viva
# DETALLES: Cada 5 segundos envia "heartbeat" y espera "OK"
# ============================================================
def heartbeat_check():
    global replica_active, replica_last_heartbeat

    while True:
        time.sleep(5)  # Esperar 5 segundos entre verificaciones

        try:
            # Crear conexion TCP con la replica
            replica_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            replica_sock.settimeout(3)
            replica_sock.connect(('localhost', REPLICA_PORT))

            # Enviar mensaje de heartbeat
            replica_sock.sendall(json.dumps({'type': 'heartbeat'}).encode())

            # Esperar respuesta "OK"
            response = replica_sock.recv(1024)
            replica_sock.close()

            if response == b"OK":
                replica_active = True
                replica_last_heartbeat = time.time()
                print("[HEARTBEAT] Replica activa")
        except:
            replica_active = False
            print("[HEARTBEAT] Replica desconectada")

# ============================================================
# FUNCION: main
# ============================================================
# PURPOSE: Punto de entrada - iniciar todos los hilos
# ============================================================
def main():
    global history

    print("=" * 50)
    print("  SERVIDOR PRINCIPAL - Chat Distribuido")
    print("=" * 50)

    # Cargar historial existente desde archivo (si existe)
    try:
        with open('historial.txt', 'r') as f:
            lines = f.readlines()
            # Tomar los ultimos MAX_HISTORY mensajes
            history = [line.strip() for line in lines[-MAX_HISTORY:]]
        print(f"[INIT] Historial cargado: {len(history)} mensajes")
    except FileNotFoundError:
        print("[INIT] No hay historial previo")

    # Hilo 1: Escuchar broadcasts UDP de descubrimiento
    thread_udp = threading.Thread(target=handle_udp_discovery)
    thread_udp.daemon = True
    thread_udp.start()

    # Hilo 2: Aceptar conexiones TCP de clientes
    thread_tcp = threading.Thread(target=handle_tcp_clients)
    thread_tcp.daemon = True
    thread_tcp.start()

    # Hilo 3: Verificar heartbeat de la replica
    thread_heartbeat = threading.Thread(target=heartbeat_check)
    thread_heartbeat.daemon = True
    thread_heartbeat.start()

    print("\nServidor iniciado. Presiona Ctrl+C para detener.")
    try:
        # Bucle principal - mantener el servidor vivo
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServidor detenido.")

if __name__ == "__main__":
    main()