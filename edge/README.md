# Agente Edge

Binario Go que valida accesos contra una copia SQLite y habla con el gateway por `ws://127.0.0.1:8080/ws`. El protocolo con la nube está congelado en [`docs/edge-protocol.md`](../docs/edge-protocol.md). La instalación está en [`docs/edge-install.md`](../docs/edge-install.md).

El gateway es un proyecto externo. Este agente se probó contra el contrato de [`docs/hardware-gateway.md`](../docs/hardware-gateway.md) y contra `edge/cmd/gateway-sim`, que implementa ese mismo contrato. No hay un número de versión del gateway dentro de este repositorio: al instalar en una sede, anote el binario probado en `gateway_version`.

```bash
cd edge
go test ./...
go run ./cmd/agent -version
go run ./cmd/gateway-sim -addr 127.0.0.1:8080
```

La normalización de lectores se comparte con el backend mediante `docs/reader-profiles/normalization-cases.json`. El intérprete Go y el de Python cubren esos casos.

`edge/tools/simulator/simulator.py` sigue siendo el simulador Python del contrato HTTP. No sustituye al binario: recorre la API sin decidir accesos ni abrir puertas.

Paquetes:

| Paquete | Responsabilidad |
| --- | --- |
| `internal/config` | `agent.yaml` y variables `EDGE_*` |
| `internal/store` | SQLite: empleados, credenciales, perfiles, puertas, cola |
| `internal/profile` | Pasos de `ReaderProfile` |
| `internal/engine` | Pipeline único para lecturas del gateway y comandos `identification` |
| `internal/gateway` | Cliente WebSocket del gateway |
| `internal/commands` | Canal de comandos, con long-poll si el WebSocket falla |
| `internal/sync` | Delta, lotes, latido y deriva de reloj |
| `internal/gatewaysim` | Gateway de prueba |
