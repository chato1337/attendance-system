package agent

import (
	"context"
	"encoding/json"

	"attendance-system/edge/internal/engine"
	"attendance-system/edge/internal/protocol"
	edgesync "attendance-system/edge/internal/sync"
)

func dispatch(ctx context.Context, command protocol.Command, eng *engine.Engine, syncer *edgesync.Syncer) map[string]any {
	payload := command.Payload
	if payload == nil {
		payload = map[string]any{}
	}
	switch command.Type {
	case "identification":
		result := eng.Handle(ctx, engine.Event{
			Source:  engine.SourceCloud,
			DoorID:  text(payload["door_id"]),
			Type:    text(payload["type"]),
			Payload: text(payload["payload"]),
		})
		return engine.Ack(result)
	case "open_door":
		result := eng.RemoteOpen(ctx, text(payload["door_id"]), text(payload["reason"]), text(payload["actor"]))
		return engine.Ack(result)
	case "sync_now":
		syncer.Nudge()
		return map[string]any{"status": "OK"}
	case "reload":
		syncer.Reload()
		return map[string]any{"status": "OK"}
	case "enrollment_mode":
		seconds, ok := integer(payload["seconds"])
		readerID := text(payload["reader_id"])
		if !ok || readerID == "" {
			return map[string]any{"status": "FAILED", "error": "payload de enrolamiento inválido"}
		}
		if err := eng.ArmEnrollment(ctx, readerID, command.ID, seconds); err != nil {
			return map[string]any{"status": "FAILED", "error": err.Error()}
		}
		return map[string]any{"status": "STARTED", "seconds": seconds}
	default:
		return map[string]any{"status": "FAILED", "error": "unsupported"}
	}
}

func text(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return ""
	}
}

func integer(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case int64:
		return int(typed), true
	case float64:
		if typed != float64(int(typed)) {
			return 0, false
		}
		return int(typed), true
	case json.Number:
		parsed, err := typed.Int64()
		if err != nil {
			return 0, false
		}
		return int(parsed), true
	default:
		return 0, false
	}
}
