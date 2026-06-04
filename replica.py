import socket
import threading
import time
import json

# ============================================================
# CONFIGURACION DE PUERTOS
# ============================================================
REPLICA_PORT = 5002     # Puerto para recibir mensajes del servidor principal
HEARTBEAT_PORT = 5003   # Puerto para recibir verificaciones de vida (heartbeat)

# ============================================================
# VARIABLES GLOBALES
# ============================================================
messages = []           # Lista de mensajes recibidos (historial en memoria)
running = True          # Bandera para controlar el bucle principal

# ============================================================
# FUNCION: handle_messages
# ============================================================
# PURPOSE: Recibir mensajes del servidor principal y almacenarlos
# FLOW:    Servidor Principal --> (TCP 5002) --> Replica
#
# Cuando llega un mensaje:
# 1. Se extrae el contenido del JSON
# 2. Se guarda en la lista 'messages' (memoria)
# 3. Se guarda en archivo 'historial_replica.txt' (persistencia)
# ============================================================
def handle_messages():
    # Crear socket TCP
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Vincular a todas las interfaces, puerto REPLICA_PORT
    server_sock.bind(('0.0.0.0', REPLICA_PORT))

    # Escuchar conexiones (backlog de 5)
    server_sock.listen(5)
    print(f"[REPLICA] Escuchando mensajes en puerto {REPLICA_PORT}")

    # Bucle infinito - siempre listo para recibir mensajes
    while running:
        try:
            # Timeout de 1 segundo para permitir verificar 'running' periodicamente
            server_sock.settimeout(1.0)

            # Aceptar conexion del servidor principal
            client_sock, addr = server_sock.accept()

            try:
                # Recibir datos (maximo 4096 bytes)
                data = client_sock.recv(4096)

                if data:
                    # Convertir JSON string a objeto Python
                    message = json.loads(data.decode())

                    # ============================================================
                    # TIPO: message (mensaje de chat)
                    # ============================================================
                    if message['type'] == 'message':
                        # Extraer contenido del mensaje
                        msg_content = message['content']

                        # Agregar a la lista en memoria
                        messages.append(msg_content)

                        # Guardar en archivo para persistencia
                        save_to_history(msg_content)

                        print(f"[REPLICA] Mensaje recibido: {msg_content}")

                    # ============================================================
                    # TIPO: sync (sincronizacion - para pedir todos los mensajes)
                    # ============================================================
                    elif message['type'] == 'sync':
                        # Enviar todos los mensajes guardados al cliente
                        for msg in messages:
                            client_sock.sendall(json.dumps({
                                'type': 'message',
                                'content': msg
                            }).encode())

            except Exception as e:
                print(f"[REPLICA] Error: {e}")

            finally:
                # Cerrar conexion con el servidor principal
                client_sock.close()

        except socket.timeout:
            # Timeout de 1 segundo, continuar el bucle
            continue

        except Exception as e:
            print(f"[REPLICA] Error en handle_messages: {e}")

# ============================================================
# FUNCION: handle_heartbeat
# ============================================================
# PURPOSE: Responder a las verificaciones de vida del servidor principal
# FLOW:    Servidor Principal --> (TCP 5003) --> Replica --> "OK"
#
# El servidor principal envia un heartbeat cada 5 segundos.
# Si la replica esta viva, responde con "OK".
# Esto demuestra tolerancia a fallos - saber cuando un nodo no responde.
# ============================================================
def handle_heartbeat():
    # Crear socket TCP
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Vincular a todas las interfaces, puerto HEARTBEAT_PORT
    server_sock.bind(('0.0.0.0', HEARTBEAT_PORT))

    # Escuchar conexiones
    server_sock.listen(5)
    print(f"[REPLICA] Heartbeat escuchando en puerto {HEARTBEAT_PORT}")

    while running:
        try:
            server_sock.settimeout(1.0)

            # Aceptar conexion del servidor principal
            client_sock, addr = server_sock.accept()

            # Recibir mensaje de heartbeat
            data = client_sock.recv(1024)

            if data:
                # Parsear JSON
                message = json.loads(data.decode())

                if message['type'] == 'heartbeat':
                    # Responder con "OK" para confirmar que estamos vivos
                    client_sock.sendall(b"OK")
                    print(f"[REPLICA] Heartbeat recibido de {addr}")

            # Cerrar conexion
            client_sock.close()

        except socket.timeout:
            continue

        except Exception as e:
            print(f"[REPLICA] Error en heartbeat: {e}")

# ============================================================
# FUNCION: save_to_history
# ============================================================
# PURPOSE: Guardar mensaje en archivo historial_replica.txt
# DETALLES: Este archivo debe coincidir con historial.txt del servidor
# ============================================================
def save_to_history(msg):
    with open('historial_replica.txt', 'a') as f:
        timestamp = time.strftime('%H:%M:%S')
        f.write(f"[{timestamp}] {msg}\n")

# ============================================================
# FUNCION: main
# ============================================================
# PURPOSE: Punto de entrada - iniciar la replica
# ============================================================
def main():
    global running

    print("=" * 50)
    print("  SERVIDOR REPLICA - Chat Distribuido")
    print("=" * 50)
    print("La replica almacena mensajes y responde heartbeats.")
    print()

    # Hilo 1: Escuchar mensajes del servidor principal
    thread_messages = threading.Thread(target=handle_messages)
    thread_messages.daemon = True
    thread_messages.start()

    # Hilo 2: Responder heartbeats del servidor principal
    thread_heartbeat = threading.Thread(target=handle_heartbeat)
    thread_heartbeat.daemon = True
    thread_heartbeat.start()

    print("\nReplica iniciada. Presiona Ctrl+C para detener.")
    try:
        # Bucle principal
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        running = False
        print("\nReplica detenida.")

if __name__ == "__main__":
    main()