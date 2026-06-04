import socket
import threading
import time
import json
import queue
import tkinter as tk
from tkinter import scrolledtext, messagebox

# ============================================================
# CONSTANTES
# ============================================================
UDP_PORT = 5000  # Puerto de descubrimiento (broadcast UDP)

# ============================================================
# VARIABLES GLOBALES
# ============================================================
server_ip = None
server_port = None
client_sock = None
running = True
message_queue = queue.Queue()  # Cola para pasar mensajes de red -> GUI


# ============================================================
# FUNCION: discover_server
# ============================================================
# PURPOSE: Encontrar el servidor usando broadcast UDP
# ============================================================
def discover_server():
    global server_ip, server_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(5.0)

    try:
        sock.sendto(b"DISCOVER_SERVER", ('<broadcast>', UDP_PORT))
        data, addr = sock.recvfrom(1024)
        server_info = data.decode()
        server_ip, server_port = server_info.split(':')
        server_port = int(server_port)
        sock.close()
        return True
    except socket.timeout:
        sock.close()
        return False
    except Exception as e:
        sock.close()
        print(f"[ERROR] Discovery: {e}")
        return False


# ============================================================
# FUNCION: receive_messages
# ============================================================
# PURPOSE: Hilo que recibe mensajes del servidor y los pone en cola
#          para que la GUI los procese
# ============================================================
def receive_messages(sock):
    global running
    buffer = ""

    while running:
        try:
            sock.settimeout(0.5)
            data = sock.recv(4096)
            if not data:
                message_queue.put(('disconnected', None))
                break

            buffer += data.decode()

            # Procesar mensajes completos (terminados en \n)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                try:
                    message = json.loads(line)
                    msg_type = message.get('type', 'message')
                    content = message.get('content', '')

                    if msg_type in ('message', 'system', 'history'):
                        message_queue.put((msg_type, content))
                except json.JSONDecodeError:
                    continue
        except socket.timeout:
            continue
        except Exception as e:
            message_queue.put(('error', str(e)))
            break


# ============================================================
# CLASE: ChatClient
# ============================================================
# PURPOSE: Ventana principal del chat con interfaz tkinter
# ============================================================
class ChatClient:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.root.title(f"Chat Distribuido - {username}")
        self.root.geometry("600x500")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # ============================================================
        # AREA DE MENSAJES (scrollable, solo lectura)
        # ============================================================
        self.chat_area = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            state='disabled',
            font=('Arial', 11),
            bg='#f5f5f5'
        )
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Tags para colores
        self.chat_area.tag_config('own', foreground='#0066cc')
        self.chat_area.tag_config('other', foreground='#000000')
        self.chat_area.tag_config('system', foreground='#888888', font=('Arial', 10, 'italic'))
        self.chat_area.tag_config('history', foreground='#555555', font=('Arial', 10))

        # ============================================================
        # AREA DE ENTRADA (campo de texto + boton enviar)
        # ============================================================
        input_frame = tk.Frame(root)
        input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)

        self.entry = tk.Entry(input_frame, font=('Arial', 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind('<Return>', lambda e: self.send_message())
        self.entry.focus()

        self.send_button = tk.Button(
            input_frame,
            text="Enviar",
            command=self.send_message,
            font=('Arial', 11),
            bg='#0066cc',
            fg='white',
            padx=15
        )
        self.send_button.pack(side=tk.LEFT)

        # Iniciar verificacion de la cola de mensajes
        self.root.after(100, self.process_queue)

    # ============================================================
    # METODO: send_message
    # ============================================================
    def send_message(self):
        msg = self.entry.get().strip()
        if not msg:
            return

        try:
            # Enviar al servidor
            data = json.dumps({'type': 'message', 'content': msg}) + '\n'
            client_sock.sendall(data.encode())

            # Mostrar mensaje propio en el chat
            self.add_message('own', f"Yo: {msg}")

            # Limpiar campo de entrada
            self.entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar: {e}")

    # ============================================================
    # METODO: add_message
    # ============================================================
    def add_message(self, msg_type, content):
        self.chat_area.config(state='normal')

        if msg_type == 'own':
            self.chat_area.insert(tk.END, content + '\n', 'own')
        elif msg_type == 'system':
            self.chat_area.insert(tk.END, f"* {content} *\n", 'system')
        elif msg_type == 'history':
            self.chat_area.insert(tk.END, f"  {content}\n", 'history')
        else:
            self.chat_area.insert(tk.END, content + '\n', 'other')

        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END)

    # ============================================================
    # METODO: process_queue
    # ============================================================
    # PURPOSE: Procesar mensajes de la cola y mostrarlos en la GUI
    #          Se ejecuta periodicamente con root.after()
    # ============================================================
    def process_queue(self):
        global running
        try:
            while True:
                msg_type, content = message_queue.get_nowait()

                if msg_type == 'disconnected':
                    messagebox.showwarning("Desconectado", "El servidor cerro la conexion")
                    self.on_closing()
                    return
                elif msg_type == 'error':
                    self.add_message('system', f"Error: {content}")
                else:
                    self.add_message(msg_type, content)
        except queue.Empty:
            pass

        if running:
            self.root.after(100, self.process_queue)

    # ============================================================
    # METODO: on_closing
    # ============================================================
    def on_closing(self):
        global running
        running = False
        try:
            if client_sock:
                client_sock.close()
        except:
            pass
        self.root.destroy()


# ============================================================
# CLASE: LoginWindow
# ============================================================
# PURPOSE: Ventana de login para pedir el nombre de usuario
# ============================================================
class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Distribuido - Login")
        self.root.geometry("400x150")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Etiqueta
        label = tk.Label(
            root,
            text="Ingresa tu nombre de usuario:",
            font=('Arial', 11)
        )
        label.pack(pady=(20, 5))

        # Campo de texto
        self.username_entry = tk.Entry(root, font=('Arial', 12), width=30)
        self.username_entry.pack(pady=5)
        self.username_entry.focus()
        self.username_entry.bind('<Return>', lambda e: self.connect())

        # Boton
        self.connect_button = tk.Button(
            root,
            text="Conectar",
            command=self.connect,
            font=('Arial', 11),
            bg='#0066cc',
            fg='white',
            padx=20,
            pady=5
        )
        self.connect_button.pack(pady=10)

        self.username = None
        self.connected = False

    def connect(self):
        global client_sock

        username = self.username_entry.get().strip()
        if not username:
            username = f"Usuario{int(time.time() % 1000)}"

        try:
            # Conectar al servidor
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.settimeout(5)
            client_sock.connect((server_ip, server_port))

            # Enviar login
            login = json.dumps({'type': 'login', 'username': username}) + '\n'
            client_sock.sendall(login.encode())

            self.username = username
            self.connected = True
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error de conexion", f"No se pudo conectar: {e}")
            if client_sock:
                try:
                    client_sock.close()
                except:
                    pass
                client_sock = None

    def on_closing(self):
        self.root.destroy()


# ============================================================
# FUNCION: main
# ============================================================
def main():
    global running

    # Paso 1: Descubrir servidor
    print("[CLIENT] Buscando servidor...")
    if not discover_server():
        print("[CLIENT] No se encontro servidor en la red")
        print("[CLIENT] Asegurate de que el servidor este corriendo")
        return

    print(f"[CLIENT] Servidor encontrado: {server_ip}:{server_port}")

    # Paso 2: Mostrar ventana de login (aqui se conecta TCP)
    login_root = tk.Tk()
    login_window = LoginWindow(login_root)
    login_root.mainloop()

    if not login_window.connected:
        print("[CLIENT] Conexion cancelada")
        return

    # Paso 3: Ahora que client_sock existe, iniciar hilo de recepcion
    thread_recv = threading.Thread(target=receive_messages, args=(client_sock,))
    thread_recv.daemon = True
    thread_recv.start()

    # Paso 4: Mostrar ventana de chat
    chat_root = tk.Tk()
    chat_client = ChatClient(chat_root, login_window.username)
    chat_root.mainloop()

    print("[CLIENT] Desconectado")


if __name__ == "__main__":
    main()