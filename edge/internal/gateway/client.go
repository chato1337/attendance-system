// Package gateway habla con el gateway serial por el WebSocket de hardware-gateway.md.
package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	replayLimit     = 50
	defaultOpenWait = 5 * time.Second
)

// Event es un hardware_read ya fuera del historial de reconexión.
type Event struct {
	DeviceID string
	Data     string
	At       time.Time
}

// Options ajusta la reconexión. Los ceros usan los valores de producción.
type Options struct {
	MinBackoff  time.Duration
	MaxBackoff  time.Duration
	OpenTimeout time.Duration
}

// Client mantiene el socket, pide listen y correlaciona open_door.
type Client struct {
	url         string
	minBackoff  time.Duration
	maxBackoff  time.Duration
	openTimeout time.Duration
	events      chan Event

	mu        sync.Mutex
	writeMu   sync.Mutex
	conn      *websocket.Conn
	connected bool
	replaying bool
	replayed  int
	listening map[string]bool
	devices   []string
	waiters   map[string][]chan error
}

// New crea un cliente desconectado. Events tiene buffer para no frenar el socket en una sola lectura.
func New(url string, options Options) *Client {
	if options.MinBackoff <= 0 {
		options.MinBackoff = time.Second
	}
	if options.MaxBackoff <= 0 {
		options.MaxBackoff = 30 * time.Second
	}
	if options.OpenTimeout <= 0 {
		options.OpenTimeout = defaultOpenWait
	}
	return &Client{
		url:         url,
		minBackoff:  options.MinBackoff,
		maxBackoff:  options.MaxBackoff,
		openTimeout: options.OpenTimeout,
		events:      make(chan Event, 64),
		listening:   map[string]bool{},
		waiters:     map[string][]chan error{},
	}
}

// Events entrega lecturas en vivo.
func (c *Client) Events() <-chan Event {
	return c.events
}

// Connected indica si el socket está abierto.
func (c *Client) Connected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}

// Ready indica que ya pasó el historial de reconexión y el socket sigue abierto.
func (c *Client) Ready() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected && !c.replaying
}

// Listening devuelve los device_id con confirmación listening.
func (c *Client) Listening() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	ids := make([]string, 0, len(c.listening))
	for id, ok := range c.listening {
		if ok {
			ids = append(ids, id)
		}
	}
	return ids
}

// SetDevices actualiza los puertos a escuchar y, si ya hay socket, envía listen.
func (c *Client) SetDevices(ids []string) {
	c.mu.Lock()
	c.devices = append([]string(nil), ids...)
	ready := c.connected && !c.replaying
	pending := append([]string(nil), ids...)
	c.mu.Unlock()
	if ready {
		c.listen(pending)
	}
}

// Open envía open_door y espera door_opened o error, con el plazo del gateway.
func (c *Client) Open(ctx context.Context, deviceID string) error {
	if deviceID == "" {
		return errors.New("device_id vacío")
	}
	c.mu.Lock()
	if !c.connected {
		c.mu.Unlock()
		return errors.New("gateway desconectado")
	}
	waiter := make(chan error, 1)
	c.waiters[deviceID] = append(c.waiters[deviceID], waiter)
	c.mu.Unlock()
	if err := c.write(map[string]string{"action": "open_door", "device_id": deviceID}); err != nil {
		c.cancelWaiter(deviceID, waiter)
		return err
	}
	timer := time.NewTimer(c.openTimeout)
	defer timer.Stop()
	select {
	case err := <-waiter:
		return err
	case <-timer.C:
		c.cancelWaiter(deviceID, waiter)
		return errors.New("el gateway no confirmó la apertura")
	case <-ctx.Done():
		c.cancelWaiter(deviceID, waiter)
		return ctx.Err()
	}
}

// Run conecta y reconecta hasta que ctx se cancela.
func (c *Client) Run(ctx context.Context) error {
	backoff := c.minBackoff
	for {
		if ctx.Err() != nil {
			c.drop(errors.New("agente detenido"))
			return nil
		}
		err := c.session(ctx)
		c.drop(err)
		if ctx.Err() != nil {
			return nil
		}
		slog.Warn("gateway desconectado", "error", err)
		timer := time.NewTimer(backoff)
		select {
		case <-ctx.Done():
			timer.Stop()
			return nil
		case <-timer.C:
		}
		backoff *= 2
		if backoff > c.maxBackoff {
			backoff = c.maxBackoff
		}
	}
}

func (c *Client) session(ctx context.Context) error {
	dialer := websocket.Dialer{HandshakeTimeout: 5 * time.Second}
	conn, response, err := dialer.DialContext(ctx, c.url, nil)
	if response != nil && response.Body != nil {
		_ = response.Body.Close()
	}
	if err != nil {
		return err
	}
	c.mu.Lock()
	c.conn = conn
	c.connected = true
	c.replaying = true
	c.replayed = 0
	c.listening = map[string]bool{}
	c.mu.Unlock()
	defer func() { _ = conn.Close() }()
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		_ = conn.SetReadDeadline(time.Now().Add(2 * time.Minute))
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var frame inbound
		if err := json.Unmarshal(payload, &frame); err != nil {
			slog.Warn("frame del gateway ilegible", "error", err)
			continue
		}
		c.dispatch(frame)
	}
}

type inbound struct {
	Event    string `json:"event"`
	Data     string `json:"data"`
	DeviceID string `json:"device_id"`
	Error    string `json:"error"`
}

func (c *Client) dispatch(frame inbound) {
	c.mu.Lock()
	if c.replaying && frame.Event != "hello" {
		if frame.Event == "clients" || c.replayed >= replayLimit {
			c.replaying = false
			devices := append([]string(nil), c.devices...)
			c.mu.Unlock()
			c.listen(devices)
			return
		}
		c.replayed++
		c.mu.Unlock()
		return
	}
	c.mu.Unlock()
	switch frame.Event {
	case "listening":
		c.mu.Lock()
		c.listening[frame.DeviceID] = true
		c.mu.Unlock()
	case "hardware_read":
		c.events <- Event{DeviceID: frame.DeviceID, Data: frame.Data, At: time.Now().UTC()}
	case "door_opened":
		c.resolve(frame.DeviceID, nil)
	case "error":
		if frame.DeviceID != "" {
			c.resolve(frame.DeviceID, errors.New(frame.Error))
		}
	}
}

func (c *Client) listen(devices []string) {
	for _, deviceID := range devices {
		if deviceID == "" {
			continue
		}
		if err := c.write(map[string]string{"action": "listen", "device_id": deviceID}); err != nil {
			slog.Warn("no se pudo pedir listen", "device_id", deviceID, "error", err)
		}
	}
}

func (c *Client) write(payload any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	c.writeMu.Lock()
	defer c.writeMu.Unlock()
	c.mu.Lock()
	conn := c.conn
	c.mu.Unlock()
	if conn == nil {
		return errors.New("gateway desconectado")
	}
	_ = conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
	return conn.WriteMessage(websocket.TextMessage, body)
}

func (c *Client) resolve(deviceID string, err error) {
	c.mu.Lock()
	queue := c.waiters[deviceID]
	if len(queue) == 0 {
		c.mu.Unlock()
		return
	}
	waiter := queue[0]
	c.waiters[deviceID] = queue[1:]
	c.mu.Unlock()
	waiter <- err
}

func (c *Client) cancelWaiter(deviceID string, waiter chan error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	queue := c.waiters[deviceID]
	filtered := queue[:0]
	for _, item := range queue {
		if item == waiter {
			continue
		}
		filtered = append(filtered, item)
	}
	c.waiters[deviceID] = filtered
}

func (c *Client) drop(cause error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.connected = false
	c.replaying = false
	c.conn = nil
	c.listening = map[string]bool{}
	for id, queue := range c.waiters {
		for _, waiter := range queue {
			waiter <- cause
		}
		delete(c.waiters, id)
	}
}
