package agent

import (
	"encoding/json"
	"net/http"
	"time"

	"attendance-system/edge/internal/commands"
	"attendance-system/edge/internal/engine"
	"attendance-system/edge/internal/gateway"
	"attendance-system/edge/internal/metrics"
	"attendance-system/edge/internal/store"
)

func routes(data *store.Store, eng *engine.Engine, gw *gateway.Client, cmd *commands.Client, collected *metrics.Metrics) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(writer http.ResponseWriter, request *http.Request) {
		queue, err := data.QueueSize(request.Context())
		if err != nil {
			http.Error(writer, "sqlite", http.StatusInternalServerError)
			return
		}
		version, err := data.LastVersion(request.Context())
		if err != nil {
			http.Error(writer, "sqlite", http.StatusInternalServerError)
			return
		}
		writeJSON(writer, http.StatusOK, map[string]any{
			"status":             "ok",
			"gateway_connected":  gw.Connected(),
			"commands_connected": cmd.Connected(),
			"queue_size":         queue,
			"last_version":       version,
		})
	})
	mux.HandleFunc("GET /metrics", func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "text/plain; version=0.0.4")
		_, _ = writer.Write([]byte(collected.Render()))
	})
	mux.HandleFunc("POST /enrollment", func(writer http.ResponseWriter, request *http.Request) {
		var body struct {
			ReaderID string `json:"reader_id"`
			Seconds  int    `json:"seconds"`
		}
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil || body.ReaderID == "" {
			http.Error(writer, "cuerpo inválido", http.StatusBadRequest)
			return
		}
		if body.Seconds == 0 {
			body.Seconds = 30
		}
		if err := eng.ArmEnrollment(request.Context(), body.ReaderID, "local", body.Seconds); err != nil {
			http.Error(writer, "no se pudo armar el enrolamiento", http.StatusInternalServerError)
			return
		}
		writeJSON(writer, http.StatusAccepted, map[string]any{
			"status":  "STARTED",
			"seconds": body.Seconds,
			"until":   time.Now().UTC().Add(time.Duration(body.Seconds) * time.Second).Format(time.RFC3339),
		})
	})
	return mux
}

func writeJSON(writer http.ResponseWriter, status int, body any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(body)
}
