// Package protocol contiene los tipos del contrato Edge v1.
package protocol

import (
	"errors"
	"time"

	"attendance-system/edge/internal/profile"
)

// Delta es una página de GET /api/v1/edge/sync/delta/.
type Delta struct {
	ServerTime       string          `json:"server_time"`
	CurrentVersion   int64           `json:"current_version"`
	NextSinceVersion int64           `json:"next_since_version"`
	HasMore          bool            `json:"has_more"`
	Employees        []Employee      `json:"employees"`
	Credentials      []Credential    `json:"credentials"`
	ReaderProfiles   []ReaderProfile `json:"reader_profiles"`
	Doors            []Door          `json:"doors"`
	Readers          []Reader        `json:"readers"`
}

// Employee es la fila de empleado del delta.
type Employee struct {
	ID           string  `json:"id"`
	DocumentID   string  `json:"document_id"`
	FirstName    string  `json:"first_name"`
	LastName     string  `json:"last_name"`
	DepartmentID *string `json:"department_id"`
	IsActive     bool    `json:"is_active"`
	IsInside     bool    `json:"is_inside"`
	Version      int64   `json:"version"`
}

// Credential es la fila de credencial del delta.
type Credential struct {
	ID         string  `json:"id"`
	EmployeeID string  `json:"employee_id"`
	Type       string  `json:"type"`
	Payload    string  `json:"payload"`
	IsActive   bool    `json:"is_active"`
	ValidFrom  *string `json:"valid_from"`
	ValidUntil *string `json:"valid_until"`
	Version    int64   `json:"version"`
}

// ReaderProfile es la fila de perfil de lector del delta.
type ReaderProfile struct {
	ID             string         `json:"id"`
	Name           string         `json:"name"`
	CredentialType string         `json:"credential_type"`
	Normalization  []profile.Step `json:"normalization"`
	MinLength      int            `json:"min_length"`
	MaxLength      int            `json:"max_length"`
	IsActive       bool           `json:"is_active"`
	Version        int64          `json:"version"`
}

// Door es la fila de puerta del delta.
type Door struct {
	ID              string  `json:"id"`
	NodeID          string  `json:"node_id"`
	ZoneID          *string `json:"zone_id"`
	Name            string  `json:"name"`
	RelayDeviceID   string  `json:"relay_device_id"`
	Direction       string  `json:"direction"`
	ApbMode         string  `json:"apb_mode"`
	FaceEnabled     bool    `json:"face_enabled"`
	RequiredFactors any     `json:"required_factors"`
	IsActive        bool    `json:"is_active"`
	Version         int64   `json:"version"`
}

// Reader es la fila de lector del delta.
type Reader struct {
	ID              string `json:"id"`
	DoorID          string `json:"door_id"`
	ReaderProfileID string `json:"reader_profile_id"`
	Name            string `json:"name"`
	ReaderDeviceID  string `json:"reader_device_id"`
	IsActive        bool   `json:"is_active"`
	Version         int64  `json:"version"`
}

// Log es una marcación generada en el Edge.
type Log struct {
	ID           string  `json:"id"`
	EmployeeID   *string `json:"employee_id,omitempty"`
	CredentialID *string `json:"credential_id,omitempty"`
	DoorID       *string `json:"door_id,omitempty"`
	Timestamp    string  `json:"timestamp"`
	Direction    string  `json:"direction"`
	Status       string  `json:"status"`
	DenialReason string  `json:"denial_reason,omitempty"`
	Method       string  `json:"method,omitempty"`
	Source       string  `json:"source,omitempty"`
}

// BatchResult es la respuesta de POST /api/v1/edge/logs/batch/.
type BatchResult struct {
	ServerTime string     `json:"server_time"`
	Accepted   []string   `json:"accepted"`
	Duplicated []string   `json:"duplicated"`
	Rejected   []Rejected `json:"rejected"`
}

// Rejected explica por qué una marcación no se guardó.
type Rejected struct {
	ID     *string `json:"id"`
	Reason string  `json:"reason"`
}

// Heartbeat es el cuerpo de POST /api/v1/edge/heartbeat/.
type Heartbeat struct {
	AgentVersion      string   `json:"agent_version"`
	GatewayConnected  bool     `json:"gateway_connected"`
	ListeningDevices  []string `json:"listening_devices"`
	QueueSize         int      `json:"queue_size"`
	LastVersion       int64    `json:"last_version"`
	CommandsConnected bool     `json:"commands_connected"`
	GatewayVersion    string   `json:"gateway_version,omitempty"`
}

// Command es un comando de la nube hacia el agente.
type Command struct {
	ID        string         `json:"id"`
	Type      string         `json:"type"`
	Payload   map[string]any `json:"payload"`
	ExpiresAt string         `json:"expires_at"`
}

// Poll es la respuesta del long-poll de comandos.
type Poll struct {
	ServerTime string    `json:"server_time"`
	Commands   []Command `json:"commands"`
}

// Timed es cualquier respuesta que trae server_time.
type Timed struct {
	ServerTime string `json:"server_time"`
}

// EnrollmentRead es una lectura capturada durante el enrolamiento asistido.
type EnrollmentRead struct {
	ReaderID       string `json:"reader_id"`
	CommandID      string `json:"command_id,omitempty"`
	Raw            string `json:"raw"`
	Payload        string `json:"payload,omitempty"`
	CredentialType string `json:"credential_type,omitempty"`
	Error          string `json:"error,omitempty"`
}

// ParseTime interpreta un instante UTC del protocolo.
func ParseTime(value string) (time.Time, error) {
	if value == "" {
		return time.Time{}, errors.New("tiempo vacío")
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		parsed, err = time.Parse(time.RFC3339, value)
		if err != nil {
			return time.Time{}, err
		}
	}
	return parsed.UTC(), nil
}

// FormatTime serializa un instante como UTC con sufijo Z.
func FormatTime(value time.Time) string {
	return value.UTC().Format(time.RFC3339Nano)
}
