package commands

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"attendance-system/edge/internal/cloud"
	"attendance-system/edge/internal/protocol"

	"github.com/gorilla/websocket"
)

func TestWebSocketDeliversAck(t *testing.T) {
	acked := make(chan string, 1)
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		conn, err := upgrader.Upgrade(writer, request, nil)
		if err != nil {
			return
		}
		defer func() { _ = conn.Close() }()
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var auth map[string]string
		if err := json.Unmarshal(payload, &auth); err != nil || auth["token"] != "secret" {
			return
		}
		_ = conn.WriteJSON(map[string]string{"op": "auth_ok", "node_id": "node"})
		_ = conn.WriteJSON(map[string]any{
			"op": "command", "id": "cmd-1", "type": "sync_now", "payload": map[string]any{},
			"expires_at": time.Now().Add(time.Minute).UTC().Format(time.RFC3339),
		})
		_, payload, err = conn.ReadMessage()
		if err != nil {
			return
		}
		var message map[string]any
		if json.Unmarshal(payload, &message) == nil && message["op"] == "ack" {
			acked <- message["id"].(string)
		}
	}))
	t.Cleanup(server.Close)
	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws/edge/"
	client := New(cloud.New(server.URL, "secret"), wsURL, func(context.Context, protocol.Command) map[string]any {
		return map[string]any{"status": "OK"}
	}, Options{MinBackoff: 20 * time.Millisecond, MaxBackoff: 40 * time.Millisecond, FailuresBeforePoll: 5})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = client.Run(ctx) }()
	select {
	case id := <-acked:
		if id != "cmd-1" {
			t.Fatalf("ack %s", id)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no llegó el ack")
	}
}

func TestFallsBackToLongPoll(t *testing.T) {
	acked := make(chan struct{}, 1)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/api/v1/edge/commands/":
			_, _ = writer.Write([]byte(`{"server_time":"2026-10-18T23:00:00Z","commands":[{"id":"cmd-2","type":"reload","payload":{},"expires_at":"2099-01-01T00:00:00Z"}]}`))
		case "/api/v1/edge/commands/cmd-2/ack/":
			writer.WriteHeader(http.StatusOK)
			_, _ = writer.Write([]byte(`{"id":"cmd-2","status":"ACKED"}`))
			acked <- struct{}{}
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(server.Close)
	client := New(cloud.New(server.URL, "secret"), "ws://127.0.0.1:1/ws/edge/", func(context.Context, protocol.Command) map[string]any {
		return map[string]any{"status": "OK"}
	}, Options{
		FailuresBeforePoll: 1,
		PollWait:           1,
		RetryWSAfter:       time.Hour,
		MinBackoff:         15 * time.Millisecond,
		MaxBackoff:         20 * time.Millisecond,
	})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = client.Run(ctx) }()
	select {
	case <-acked:
	case <-time.After(3 * time.Second):
		t.Fatal("el long-poll no confirmó el comando")
	}
}
