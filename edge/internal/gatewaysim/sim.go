// Package gatewaysim implementa el contrato WebSocket del gateway para pruebas y demos.
package gatewaysim

import (
	"encoding/json"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Frame es un mensaje de salida del gateway.
type Frame struct {
	Event    string `json:"event"`
	Action   string `json:"action,omitempty"`
	Data     string `json:"data,omitempty"`
	DeviceID string `json:"device_id,omitempty"`
	Error    string `json:"error,omitempty"`
}

// Server es un gateway de mentira.
type Server struct {
	URL   string
	Pulse time.Duration

	mu       sync.Mutex
	history  []Frame
	failOpen map[string]string
	conns    map[*websocket.Conn]struct{}
	listened []string
	server   *http.Server
}

var upgrader = websocket.Upgrader{
	CheckOrigin: func(*http.Request) bool { return true },
}

// Start escucha en 127.0.0.1 en un puerto libre, camino /ws.
func Start() (*Server, error) {
	return StartAddr("127.0.0.1:0")
}

// StartAddr escucha en addr. Un puerto 0 lo elige el sistema.
func StartAddr(addr string) (*Server, error) {
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, err
	}
	sim := &Server{
		URL:      "ws://" + listener.Addr().String() + "/ws",
		Pulse:    10 * time.Millisecond,
		failOpen: map[string]string{},
		conns:    map[*websocket.Conn]struct{}{},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", sim.serveWS)
	mux.HandleFunc("/inject", sim.serveInject)
	sim.server = &http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() { _ = sim.server.Serve(listener) }()
	return sim, nil
}

// SetHistory define los eventos que se reenvían justo después de hello.
func (s *Server) SetHistory(frames []Frame) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.history = append([]Frame(nil), frames...)
}

// FailOpen hace que open_door de ese puerto responda error.
func (s *Server) FailOpen(deviceID, message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failOpen[deviceID] = message
}

// Inject emite un hardware_read a los clientes conectados.
func (s *Server) Inject(deviceID, data string) {
	s.broadcast(Frame{Event: "hardware_read", DeviceID: deviceID, Data: data})
}

// Listened devuelve los device_id para los que alguien pidió listen.
func (s *Server) Listened() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]string(nil), s.listened...)
}

// Close apaga el servidor.
func (s *Server) Close() error {
	s.mu.Lock()
	for conn := range s.conns {
		_ = conn.Close()
	}
	s.mu.Unlock()
	if s.server == nil {
		return nil
	}
	return s.server.Close()
}

func (s *Server) serveInject(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		http.Error(writer, "method", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		DeviceID string `json:"device_id"`
		Data     string `json:"data"`
	}
	if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
		http.Error(writer, "json", http.StatusBadRequest)
		return
	}
	s.Inject(body.DeviceID, body.Data)
	writer.WriteHeader(http.StatusNoContent)
}

func (s *Server) serveWS(writer http.ResponseWriter, request *http.Request) {
	conn, err := upgrader.Upgrade(writer, request, nil)
	if err != nil {
		return
	}
	s.mu.Lock()
	s.conns[conn] = struct{}{}
	history := append([]Frame(nil), s.history...)
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		delete(s.conns, conn)
		s.mu.Unlock()
		_ = conn.Close()
	}()
	_ = write(conn, Frame{Event: "hello", Data: "1"})
	for _, frame := range history {
		_ = write(conn, frame)
	}
	_ = write(conn, Frame{Event: "clients", Data: "1"})
	for {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var command struct {
			Action   string `json:"action"`
			DeviceID string `json:"device_id"`
		}
		if err := json.Unmarshal(payload, &command); err != nil {
			_ = write(conn, Frame{Event: "error", Error: "json inválido"})
			continue
		}
		switch command.Action {
		case "listen":
			s.mu.Lock()
			s.listened = append(s.listened, command.DeviceID)
			s.mu.Unlock()
			s.broadcast(Frame{Event: "listening", Action: "listen", DeviceID: command.DeviceID})
		case "open_door":
			s.mu.Lock()
			message := s.failOpen[command.DeviceID]
			pulse := s.Pulse
			s.mu.Unlock()
			if message != "" {
				_ = write(conn, Frame{Event: "error", Action: "open_door", DeviceID: command.DeviceID, Error: message})
				continue
			}
			time.Sleep(pulse)
			s.broadcast(Frame{Event: "door_opened", Action: "open_door", DeviceID: command.DeviceID})
		default:
			_ = write(conn, Frame{Event: "error", Action: command.Action, DeviceID: command.DeviceID, Error: "acción no simulada"})
		}
	}
}

func (s *Server) broadcast(frame Frame) {
	s.mu.Lock()
	conns := make([]*websocket.Conn, 0, len(s.conns))
	for conn := range s.conns {
		conns = append(conns, conn)
	}
	s.mu.Unlock()
	for _, conn := range conns {
		_ = write(conn, frame)
	}
}

func write(conn *websocket.Conn, frame Frame) error {
	body, err := json.Marshal(frame)
	if err != nil {
		return err
	}
	_ = conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
	if err := conn.WriteMessage(websocket.TextMessage, body); err != nil {
		return err
	}
	return nil
}
