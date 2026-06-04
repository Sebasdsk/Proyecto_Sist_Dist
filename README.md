# Chat Distribuido

Sistema de chat cliente-servidor con descubrimiento automático de servidores, réplica de mensajes y detección de fallos por heartbeat.

## Descripción

Este proyecto implementa una aplicación de chat donde múltiples clientes pueden conectarse a un servidor en la red, comunicarse entre sí y ver el historial de mensajes. El sistema incluye un servidor réplica que almacena copias de seguridad de los mensajes y un mecanismo de heartbeat para detectar si algún nodo deja de responder.

## Características Principales

- **Descubrimiento automático**: Los clientes encuentran el servidor en la red mediante broadcast UDP, sin necesidad de configurar direcciones IP manualmente.
- **Chat en tiempo real**: Los mensajes se distribuyen instantáneamente a todos los clientes conectados.
- **Historial de mensajes**: Al conectarse, cada cliente puede ver los últimos 50 mensajes enviados antes de su llegada.
- **Réplica de mensajes**: El servidor principal envía una copia de cada mensaje a un servidor réplica para respaldo.
- **Detección de fallos**: Verificación periódica (heartbeat cada 5 segundos) para saber si la réplica sigue activa.
- **Interfaz gráfica**: El cliente cuenta con una ventana de chat simple construida con tkinter.

## Arquitectura

```
┌─────────────┐      UDP Broadcast      ┌─────────────────┐
│  Cliente 1  │ ◄────────────────────► │                 │
├─────────────┤                        │  Servidor       │
│  Cliente 2  │ ◄──── TCP Chat ──────► │  Principal      │
├─────────────┤                        │  (Puerto 5001)  │
│  Cliente N  │                        │                 │
└─────────────┘                        └────────┬────────┘
                                                  │
                                                  │ TCP Replica
                                                  ▼
                                         ┌─────────────────┐
                                         │  Servidor       │
                                         │  Réplica        │
                                         │  (Puerto 5002)  │
                                         └─────────────────┘
```

## Archivos del Proyecto

| Archivo | Descripción |
|---------|-------------|
| `servidor.py` | Servidor principal: acepta clientes, distribuye mensajes, envía réplica y verifica heartbeat |
| `replica.py` | Servidor réplica: recibe copias de mensajes y responde heartbeats |
| `cliente.py` | Cliente con GUI: descubre servidor, conecta y permite enviar/recibir mensajes |
| `historial.txt` | Archivo de mensajes generado por el servidor principal |
| `historial_replica.txt` | Copia de respaldo generada por la réplica |

## Requisitos

- Python 3.6 o superior
- tkinter (incluido por defecto en la mayoría de distribuciones Python)
- Todos los equipos deben estar en la misma red local

## Cómo Ejecutar

### 1. Iniciar la Réplica

En una terminal ejecuta:

```bash
python3 replica.py
```

### 2. Iniciar el Servidor Principal

En otra terminal ejecuta:

```bash
python3 servidor.py
```

### 3. Conectar Clientes

Cada cliente debe abrir su propia terminal y ejecutar:

```bash
python3 cliente.py
```

Aparecerá una ventana de login. Ingresa un nombre de usuario y presiona **Conectar**.

> **Nota**: Puedes abrir tantos clientes como quieras, cada uno en su propia terminal/ventana.

## Uso del Cliente

1. Al iniciar, el cliente busca automáticamente el servidor en la red.
2. Ingresa tu nombre de usuario en la ventana de login.
3. En la ventana de chat verás los últimos mensajes del historial.
4. Escribe tu mensaje en el campo inferior y presiona **Enviar** (o Enter).
5. Cierra la ventana para salir del chat.

## Protocolo de Comunicación

- **UDP Broadcast**: Los clientes envían `DISCOVER_SERVER` al puerto 5000. El servidor responde con `IP:PUERTO_TCP`.
- **Mensajes TCP**: Todos los mensajes se envían en formato JSON terminados con `\n` (newline).
- **Tipos de mensaje**:
  - `login`: Registro del cliente con su nombre de usuario.
  - `message`: Mensaje de chat normal.
  - `system`: Notificaciones de conexión/desconexión.
  - `history`: Mensajes históricos enviados al conectarse.
  - `heartbeat`: Señal de vida enviada cada 5 segundos.

