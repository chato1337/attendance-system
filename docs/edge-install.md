# Instalación del agente Edge

El agente es un binario aparte del gateway. El gateway sigue en su repositorio y solo se habla con él por `ws://127.0.0.1:8080/ws` (o `wss` si no se usa `-http`). El contrato es el de [`hardware-gateway.md`](hardware-gateway.md). Este repositorio no fija un número de versión del gateway porque ese proyecto no se publica aquí: el campo `gateway_version` de `agent.yaml` es el que el instalador anota tras probar el binario concreto.

El reloj del puesto debe usar NTP (`chrony` en Linux, `w32time` en Windows). Si la deriva contra `server_time` supera `clock_skew_threshold` (5 s por defecto), el agente lo deja en el log.

## Compilar

Hace falta Go 1.23.

```bash
cd edge
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o bin/agent ./cmd/agent
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o bin/agent-arm64 ./cmd/agent
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o bin/agent.exe ./cmd/agent
```

El simulador del gateway, para una sede sin hardware:

```bash
go build -o bin/gateway-sim ./cmd/gateway-sim
./bin/gateway-sim -addr 127.0.0.1:8080
```

`POST http://127.0.0.1:8080/inject` con `{"device_id":"COM3","data":"AB12"}` emite un `hardware_read`.

## Configuración

Copie [`edge/agent.yaml.example`](../edge/agent.yaml.example). Estas variables pisan el archivo si están definidas: `EDGE_CLOUD_URL`, `EDGE_API_KEY`, `EDGE_GATEWAY_URL`, `EDGE_SQLITE_PATH`, `EDGE_LISTEN_ADDR`.

La API key es la del nodo, la que la nube muestra una sola vez. El agente la usa como `Authorization: Bearer` y como primer mensaje del WebSocket de comandos.

## Linux

`edge/deploy/install.sh` copia el binario, la unidad systemd y un `agent.yaml` si no existe. Hay que crear el usuario `attendance` antes de arrancar el servicio. Si `GATEWAY_BIN` apunta al gateway real, el script solo imprime el arranque sugerido: el puerto tiene que quedar en loopback.

```bash
sudo useradd --system --home /var/lib/attendance --shell /usr/sbin/nologin attendance
sudo env GATEWAY_BIN=/usr/local/bin/gateway ./edge/deploy/install.sh
sudo systemctl start attendance-agent
```

## Windows

`edge/deploy/install-windows.ps1` registra una tarea al inicio. No es un servicio del Administrador de servicios: el binario no habla con el SCM.

## Salud local

En `127.0.0.1:9090`:

| Ruta | Uso |
| --- | --- |
| `GET /healthz` | JSON con cola, cursor y si el gateway y el canal de comandos están conectados |
| `GET /metrics` | Texto Prometheus (latencia de validación, cola, conexión) |
| `POST /enrollment` | Arma el enrolamiento asistido de un lector sin esperar un comando de la nube. Cuerpo: `{"reader_id","seconds"}` |

Ese puerto no debe salir de la máquina.

## Qué hace el proceso

1. Al arrancar baja el delta y escucha los `reader_device_id` activos.
2. Cada `hardware_read` se normaliza con el perfil del lector y se decide en local. Si se concede, envía `open_door` al relé.
3. Al reconectar ignora el historial que el gateway reenvía (hasta 50 eventos, hasta el mensaje `clients`) para no repetir lecturas viejas.
4. La cola de marcaciones sube por lotes. Un reenvío no duplica filas: el `id` nace en el agente.
5. Los comandos `identification`, `open_door`, `sync_now`, `enrollment_mode` y `reload` llegan por `ws://<nube>/ws/edge/`. Si el WebSocket falla tres veces, usa el long-poll y vuelve a probar el socket al minuto.
6. `enrollment_mode` (o `POST /enrollment`) deja el lector en captura durante los segundos pedidos. Las lecturas no abren la puerta: se publican en `POST /api/v1/edge/enrollment-reads/`.
7. `reload` vuelve a bajar todo desde la versión 0 y borra localmente lo que la nube ya no entrega a ese nodo.

La latencia que exige la fase (p95 de validación por debajo de 200 ms) se mide hasta el momento de decidir, antes de esperar el pulso del relé. El informe del equipo objetivo está en [`edge-latency.md`](edge-latency.md).
