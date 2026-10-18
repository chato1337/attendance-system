// Package engine valida un acceso contra la copia local y, si corresponde, abre la puerta.
package engine

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"attendance-system/edge/internal/metrics"
	"attendance-system/edge/internal/profile"
	"attendance-system/edge/internal/store"

	"github.com/google/uuid"
)

const (
	// StatusGranted es un acceso concedido.
	StatusGranted = "GRANTED"
	// StatusDenied es un acceso denegado.
	StatusDenied = "DENIED"
	// StatusFailed indica que el comando no se pudo ejecutar.
	StatusFailed = "FAILED"
	// StatusEnrollment indica que la lectura se capturó para enrolar.
	StatusEnrollment = "ENROLLMENT"

	// SourceGateway es una lectura del puerto serial.
	SourceGateway = "gateway"
	// SourceCloud es un comando de identificación.
	SourceCloud = "cloud"
	// SourceRemote es una apertura pedida desde el panel.
	SourceRemote = "remote"

	reasonUnknownCredential = "UNKNOWN_CREDENTIAL"
	reasonInactive          = "INACTIVE"
	reasonExpired           = "EXPIRED"
	reasonAPB               = "APB_VIOLATION"
	reasonUnknownDevice     = "UNKNOWN_DEVICE"
	reasonMalformed         = "MALFORMED_READ"
	reasonFace              = "FACE_NOT_ALLOWED"
	reasonUnknownDoor       = "unknown_door"

	apbOff  = "OFF"
	apbSoft = "SOFT"
	apbHard = "HARD"
)

// Event es una identificación, venga del gateway o de la nube.
type Event struct {
	Source   string
	DeviceID string
	Raw      string
	DoorID   string
	Type     string
	Payload  string
	At       time.Time
}

// Result es la decisión y el efecto sobre el relé.
type Result struct {
	Status       string
	DenialReason string
	Direction    string
	Method       string
	Source       string
	EmployeeID   string
	CredentialID string
	DoorID       string
	LogID        string
	Opened       bool
	Validation   time.Duration
}

// Relay envía open_door al gateway.
type Relay interface {
	Open(ctx context.Context, deviceID string) error
}

// Reporter entrega lecturas de enrolamiento a la nube.
type Reporter interface {
	ReportEnrollment(ctx context.Context, sample store.EnrollmentSample) error
}

// Engine aplica el pipeline único de acceso.
type Engine struct {
	store    *store.Store
	relay    Relay
	reporter Reporter
	metrics  *metrics.Metrics
	mu       sync.Mutex
}

// New construye el motor.
func New(data *store.Store, relay Relay, reporter Reporter, collected *metrics.Metrics) *Engine {
	if collected == nil {
		collected = metrics.New()
	}
	return &Engine{store: data, relay: relay, reporter: reporter, metrics: collected}
}

// Handle procesa una identificación.
func (e *Engine) Handle(ctx context.Context, event Event) Result {
	e.mu.Lock()
	defer e.mu.Unlock()
	started := time.Now()
	moment := event.At
	if moment.IsZero() {
		moment = started
	}
	moment = moment.UTC()
	if event.Source == SourceCloud {
		return e.handleCloud(ctx, event, moment, started)
	}
	return e.handleGateway(ctx, event, moment, started)
}

// RemoteOpen abre una puerta sin empleado, por pedido del panel.
func (e *Engine) RemoteOpen(ctx context.Context, doorID, reason, actor string) Result {
	e.mu.Lock()
	defer e.mu.Unlock()
	started := time.Now()
	door, ok, err := e.store.LookupDoor(ctx, doorID)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: SourceRemote}
	}
	if !ok {
		return Result{Status: StatusFailed, DenialReason: reasonUnknownDoor, Source: SourceRemote}
	}
	if !door.IsActive {
		result := e.record(ctx, decision{
			status: StatusDenied, reason: reasonInactive, direction: door.Direction,
			method: "REMOTE", source: SourceRemote, doorID: door.ID,
			raw: "remote reason=" + reason + " actor=" + actor,
		}, started, time.Now().UTC())
		return result
	}
	result := e.record(ctx, decision{
		status: StatusGranted, direction: door.Direction, method: "REMOTE", source: SourceRemote,
		doorID: door.ID, relay: door.RelayDeviceID,
		raw: "remote reason=" + reason + " actor=" + actor,
	}, started, time.Now().UTC())
	result.Opened = e.open(ctx, door.RelayDeviceID)
	return result
}

// ArmEnrollment abre la ventana de enrolamiento de un lector.
func (e *Engine) ArmEnrollment(ctx context.Context, readerID, commandID string, seconds int) error {
	if seconds < 1 {
		seconds = 1
	}
	if seconds > 600 {
		seconds = 600
	}
	return e.store.ArmEnrollment(ctx, readerID, commandID, time.Now().UTC().Add(time.Duration(seconds)*time.Second))
}

func (e *Engine) handleGateway(ctx context.Context, event Event, moment, started time.Time) Result {
	view, ok, err := e.store.LookupReader(ctx, event.DeviceID)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: SourceGateway}
	}
	if !ok {
		return e.record(ctx, decision{
			status: StatusDenied, reason: reasonUnknownDevice, direction: "IN", source: SourceGateway, raw: event.Raw,
		}, started, moment)
	}
	if !view.ReaderActive || !view.Door.IsActive || !view.ProfileActive {
		return e.record(ctx, decision{
			status: StatusDenied, reason: reasonInactive, direction: view.Door.Direction,
			source: SourceGateway, doorID: view.Door.ID, raw: event.Raw,
		}, started, moment)
	}
	if commandID, armed, err := e.store.Enrollment(ctx, view.ReaderID, moment); err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: SourceGateway}
	} else if armed {
		e.captureEnrollment(ctx, view, event.Raw, commandID)
		return Result{Status: StatusEnrollment, DoorID: view.Door.ID, Source: SourceGateway, Method: view.CredentialType}
	}
	payload, err := profile.Apply(event.Raw, view.Steps, view.MinLength, view.MaxLength)
	if err != nil {
		slog.Info("lectura mal formada", "device_id", event.DeviceID, "raw", event.Raw, "error", err)
		return e.record(ctx, decision{
			status: StatusDenied, reason: reasonMalformed, direction: view.Door.Direction,
			source: SourceGateway, doorID: view.Door.ID, method: view.CredentialType, raw: event.Raw,
		}, started, moment)
	}
	return e.authorize(ctx, view.Door, view.CredentialType, payload, SourceGateway, moment, started, event.Raw)
}

func (e *Engine) handleCloud(ctx context.Context, event Event, moment, started time.Time) Result {
	door, ok, err := e.store.LookupDoor(ctx, event.DoorID)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: SourceCloud}
	}
	if !ok {
		return Result{Status: StatusFailed, DenialReason: reasonUnknownDoor, Source: SourceCloud, DoorID: event.DoorID}
	}
	if !door.IsActive {
		return e.record(ctx, decision{
			status: StatusDenied, reason: reasonInactive, direction: door.Direction,
			method: event.Type, source: SourceCloud, doorID: door.ID,
		}, started, moment)
	}
	if event.Type == "FACIAL" && !door.FaceEnabled {
		return e.record(ctx, decision{
			status: StatusDenied, reason: reasonFace, direction: door.Direction,
			method: event.Type, source: SourceCloud, doorID: door.ID,
		}, started, moment)
	}
	return e.authorize(ctx, door, event.Type, event.Payload, SourceCloud, moment, started, "")
}

func (e *Engine) authorize(ctx context.Context, door store.Door, credentialType, payload, source string, moment, started time.Time, raw string) Result {
	base := decision{
		direction: door.Direction, method: credentialType, source: source, doorID: door.ID, relay: door.RelayDeviceID, raw: raw,
	}
	credential, ok, err := e.store.LookupCredential(ctx, credentialType, payload)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: source, DoorID: door.ID}
	}
	if !ok {
		base.status = StatusDenied
		base.reason = reasonUnknownCredential
		return e.record(ctx, base, started, moment)
	}
	base.credentialID = credential.ID
	base.employeeID = credential.EmployeeID
	if !credential.IsActive {
		base.status = StatusDenied
		base.reason = reasonInactive
		return e.record(ctx, base, started, moment)
	}
	exists, active, err := e.store.EmployeeActive(ctx, credential.EmployeeID)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: source, DoorID: door.ID}
	}
	if !exists || !active {
		base.status = StatusDenied
		base.reason = reasonInactive
		return e.record(ctx, base, started, moment)
	}
	if !within(moment, credential.ValidFrom, credential.ValidUntil) {
		base.status = StatusDenied
		base.reason = reasonExpired
		return e.record(ctx, base, started, moment)
	}
	inside, err := e.store.State(ctx, credential.EmployeeID)
	if err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: source, DoorID: door.ID}
	}
	if door.Direction == "IN" && inside && door.ApbMode != apbOff {
		if door.ApbMode == apbHard {
			base.status = StatusDenied
			base.reason = reasonAPB
			base.relay = ""
			return e.record(ctx, base, started, moment)
		}
		if door.ApbMode == apbSoft {
			base.reason = reasonAPB
		}
	}
	base.status = StatusGranted
	nextInside := door.Direction == "IN"
	if err := e.store.SaveState(ctx, credential.EmployeeID, nextInside, moment); err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: source, DoorID: door.ID}
	}
	result := e.record(ctx, base, started, moment)
	result.Opened = e.open(ctx, base.relay)
	return result
}

type decision struct {
	status       string
	reason       string
	direction    string
	method       string
	source       string
	employeeID   string
	credentialID string
	doorID       string
	relay        string
	raw          string
}

func (e *Engine) record(ctx context.Context, item decision, started, at time.Time) Result {
	logID := uuid.NewString()
	if err := e.store.EnqueueLog(ctx, store.Log{
		ID: logID, EmployeeID: item.employeeID, CredentialID: item.credentialID, DoorID: item.doorID,
		Timestamp: at, Direction: item.direction, Status: item.status, DenialReason: item.reason,
		Method: item.method, Source: item.source, Raw: item.raw,
	}); err != nil {
		return Result{Status: StatusFailed, DenialReason: err.Error(), Source: item.source, DoorID: item.doorID}
	}
	elapsed := time.Since(started)
	e.metrics.ObserveValidation(item.source, elapsed)
	return Result{
		Status: item.status, DenialReason: item.reason, Direction: item.direction, Method: item.method,
		Source: item.source, EmployeeID: item.employeeID, CredentialID: item.credentialID, DoorID: item.doorID,
		LogID: logID, Validation: elapsed,
	}
}

func (e *Engine) open(ctx context.Context, deviceID string) bool {
	if deviceID == "" || e.relay == nil {
		return false
	}
	if err := e.relay.Open(ctx, deviceID); err != nil {
		slog.Warn("el relé no abrió", "device_id", deviceID, "error", err)
		return false
	}
	return true
}

func (e *Engine) captureEnrollment(ctx context.Context, view store.ReaderView, raw, commandID string) {
	payload, err := profile.Apply(raw, view.Steps, view.MinLength, view.MaxLength)
	sample := store.EnrollmentSample{
		ReaderID: view.ReaderID, CommandID: commandID, Raw: raw, CredentialType: view.CredentialType,
	}
	if err != nil {
		sample.Error = err.Error()
	} else {
		sample.Payload = payload
	}
	id, insertErr := e.store.EnqueueEnrollment(ctx, sample)
	if insertErr != nil {
		slog.Warn("no se pudo guardar la lectura de enrolamiento", "error", insertErr)
		return
	}
	sample.ID = id
	if e.reporter == nil {
		return
	}
	if err := e.reporter.ReportEnrollment(ctx, sample); err != nil {
		slog.Warn("la nube no recibió la lectura de enrolamiento", "error", err)
		return
	}
	if err := e.store.DeleteEnrollment(ctx, []int64{id}); err != nil {
		slog.Warn("no se pudo confirmar la lectura de enrolamiento", "error", err)
	}
}

func within(moment time.Time, from, until *time.Time) bool {
	if from != nil && moment.Before(from.UTC()) {
		return false
	}
	if until != nil && moment.After(until.UTC()) {
		return false
	}
	return true
}

// Ack convierte la decisión al cuerpo que espera el canal de comandos.
func Ack(result Result) map[string]any {
	if result.Status == StatusFailed {
		reason := result.DenialReason
		if reason == "" {
			reason = "error"
		}
		return map[string]any{"status": StatusFailed, "error": reason}
	}
	if result.Status == StatusEnrollment {
		return map[string]any{"status": StatusEnrollment}
	}
	body := map[string]any{
		"status":      result.Status,
		"door_opened": result.Opened,
		"log_id":      result.LogID,
	}
	if result.DenialReason != "" {
		body["denial_reason"] = result.DenialReason
	}
	return body
}
