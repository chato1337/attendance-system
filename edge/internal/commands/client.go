// Package commands recibe comandos de la nube por WebSocket y, si ese canal falla, por long-poll.
package commands

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/url"
	"sync"
	"time"

	"attendance-system/edge/internal/cloud"
	"attendance-system/edge/internal/protocol"

	"github.com/gorilla/websocket"
)

// Handler ejecuta un comando y devuelve el cuerpo del ack.
type Handler func(context.Context, protocol.Command) map[string]any

// Options ajusta los reintentos. Los ceros usan los valores de producción.
type Options struct {
	FailuresBeforePoll int
	PollWait           int
	RetryWSAfter       time.Duration
	MinBackoff         time.Duration
	MaxBackoff         time.Duration
}

// Client mantiene el canal de comandos.
type Client struct {
	cloud   *cloud.Client
	wsURL   string
	handler Handler
	options Options

	mu        sync.Mutex
	connected bool
}

// WebSocketURL deriva ws://host/ws/edge/ desde el origen HTTP de la nube.
func WebSocketURL(cloudURL string) (string, error) {
	parsed, err := url.Parse(cloudURL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "https":
		parsed.Scheme = "wss"
	default:
		parsed.Scheme = "ws"
	}
	parsed.Path = "/ws/edge/"
	parsed.RawQuery = ""
	parsed.Fragment = ""
	return parsed.String(), nil
}

// New crea el cliente. Falla de URL se informa en Run.
func New(api *cloud.Client, wsURL string, handler Handler, options Options) *Client {
	if options.FailuresBeforePoll <= 0 {
		options.FailuresBeforePoll = 3
	}
	if options.PollWait <= 0 {
		options.PollWait = 25
	}
	if options.RetryWSAfter <= 0 {
		options.RetryWSAfter = time.Minute
	}
	if options.MinBackoff <= 0 {
		options.MinBackoff = time.Second
	}
	if options.MaxBackoff <= 0 {
		options.MaxBackoff = 30 * time.Second
	}
	return &Client{cloud: api, wsURL: wsURL, handler: handler, options: options}
}

// Connected indica si el canal actual está operativo.
func (c *Client) Connected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}

func (c *Client) setConnected(value bool) {
	c.mu.Lock()
	c.connected = value
	c.mu.Unlock()
}

// Run alterna WebSocket y long-poll hasta que ctx se cancela.
func (c *Client) Run(ctx context.Context) error {
	failures := 0
	polling := false
	retryWS := time.Time{}
	backoff := c.options.MinBackoff
	for {
		if ctx.Err() != nil {
			c.setConnected(false)
			return nil
		}
		if polling && time.Now().After(retryWS) {
			polling = false
			failures = 0
		}
		var err error
		if polling {
			err = c.pollOnce(ctx)
		} else {
			err = c.session(ctx)
		}
		c.setConnected(false)
		if ctx.Err() != nil {
			return nil
		}
		if err != nil {
			slog.Warn("canal de comandos interrumpido", "error", err, "long_poll", polling)
		}
		if !polling {
			failures++
			if failures >= c.options.FailuresBeforePoll {
				polling = true
				retryWS = time.Now().Add(c.options.RetryWSAfter)
				slog.Info("comandos por long-poll", "reintento_ws", c.options.RetryWSAfter.String())
			}
		}
		timer := time.NewTimer(backoff)
		select {
		case <-ctx.Done():
			timer.Stop()
			c.setConnected(false)
			return nil
		case <-timer.C:
		}
		backoff *= 2
		if backoff > c.options.MaxBackoff {
			backoff = c.options.MaxBackoff
		}
		if err == nil {
			backoff = c.options.MinBackoff
		}
	}
}

func (c *Client) session(ctx context.Context) error {
	dialer := websocket.Dialer{HandshakeTimeout: 5 * time.Second}
	conn, response, err := dialer.DialContext(ctx, c.wsURL, nil)
	if response != nil && response.Body != nil {
		_ = response.Body.Close()
	}
	if err != nil {
		return err
	}
	defer func() { _ = conn.Close() }()
	sessionCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	writes := make(chan []byte, 16)
	writeErr := make(chan error, 1)
	go c.writeLoop(sessionCtx, conn, writes, writeErr)
	auth, err := json.Marshal(map[string]string{"op": "auth", "token": tokenOf(c.cloud)})
	if err != nil {
		return err
	}
	writes <- auth
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		_ = conn.SetReadDeadline(time.Now().Add(45 * time.Second))
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		select {
		case err := <-writeErr:
			return err
		default:
		}
		var frame inbound
		if err := json.Unmarshal(payload, &frame); err != nil {
			continue
		}
		switch frame.Op {
		case "auth_ok":
			c.setConnected(true)
		case "command":
			c.acknowledge(ctx, writes, frame.Command)
		case "ping":
			pong, err := json.Marshal(map[string]string{"op": "pong"})
			if err == nil {
				writes <- pong
			}
		case "error":
			slog.Warn("el canal de comandos rechazó un mensaje", "detail", frame.Detail)
		}
	}
}

func (c *Client) writeLoop(ctx context.Context, conn *websocket.Conn, writes <-chan []byte, writeErr chan error) {
	ticker := time.NewTicker(20 * time.Second)
	defer ticker.Stop()
	ping, err := json.Marshal(map[string]string{"op": "ping"})
	if err != nil {
		return
	}
	for {
		select {
		case <-ctx.Done():
			return
		case payload := <-writes:
			if err := writeFrame(conn, payload); err != nil {
				select {
				case writeErr <- err:
				default:
				}
				return
			}
		case <-ticker.C:
			if err := writeFrame(conn, ping); err != nil {
				select {
				case writeErr <- err:
				default:
				}
				return
			}
		}
	}
}

func writeFrame(conn *websocket.Conn, payload []byte) error {
	_ = conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
	return conn.WriteMessage(websocket.TextMessage, payload)
}

func (c *Client) acknowledge(ctx context.Context, writes chan []byte, command protocol.Command) {
	result := c.safeHandle(ctx, command)
	body, err := json.Marshal(map[string]any{"op": "ack", "id": command.ID, "result": result})
	if err != nil {
		return
	}
	select {
	case writes <- body:
	case <-ctx.Done():
	}
}

func (c *Client) pollOnce(ctx context.Context) error {
	page, err := c.cloud.Poll(ctx, c.options.PollWait)
	if err != nil {
		return err
	}
	c.setConnected(true)
	for _, command := range page.Commands {
		result := c.safeHandle(ctx, command)
		if err := c.cloud.Ack(ctx, command.ID, result); err != nil {
			slog.Warn("no se pudo confirmar el comando", "id", command.ID, "error", err)
		}
	}
	return nil
}

func (c *Client) safeHandle(ctx context.Context, command protocol.Command) (result map[string]any) {
	defer func() {
		if recovered := recover(); recovered != nil {
			slog.Error("el comando provocó un pánico", "id", command.ID, "panic", recovered)
			result = map[string]any{"status": "FAILED", "error": "panic"}
		}
	}()
	if expired(command.ExpiresAt) {
		return map[string]any{"status": "FAILED", "error": "expired"}
	}
	if c.handler == nil {
		return map[string]any{"status": "FAILED", "error": "sin manejador"}
	}
	result = c.handler(ctx, command)
	if result == nil {
		result = map[string]any{"status": "FAILED", "error": "sin resultado"}
	}
	return result
}

type inbound struct {
	Op     string `json:"op"`
	Detail string `json:"detail"`
	protocol.Command
}

func expired(value string) bool {
	if value == "" {
		return false
	}
	moment, err := protocol.ParseTime(value)
	if err != nil {
		return false
	}
	return time.Now().After(moment)
}

func tokenOf(api *cloud.Client) string {
	if api == nil {
		return ""
	}
	return api.Token()
}
