# Agente Edge

Binario Go que, en fases posteriores, valida accesos offline contra SQLite y habla con el gateway por `ws://127.0.0.1:8080/ws`.

En la fase de fundaciones el comando solo confirma que el módulo compila:

```bash
cd edge
go test ./...
go run ./cmd/agent
go run ./cmd/agent -version
```

La normalización de lectores se comparte con el backend mediante `docs/reader-profiles/normalization-cases.json`. El intérprete en Go llega con el agente (Fase 3).
