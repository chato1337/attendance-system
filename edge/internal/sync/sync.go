// Package edgesync baja el delta, sube marcaciones y late contra la nube.
package edgesync

import (
	"context"
	"log/slog"
	"time"

	"attendance-system/edge/internal/cloud"
	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
)

// Syncer ejecuta los tres ciclos del agente.
type Syncer struct {
	Store             *store.Store
	Cloud             *cloud.Client
	DeltaEvery        time.Duration
	PushEvery         time.Duration
	HeartbeatEvery    time.Duration
	Batch             int
	Retention         time.Duration
	SkewLimit         time.Duration
	Version           string
	GatewayVersion    string
	GatewayConnected  func() bool
	Listening         func() []string
	CommandsConnected func() bool
	OnSynced          func()

	nudge   chan struct{}
	reload  chan struct{}
	pushNow chan struct{}
}

// New prepara los canales de aviso. Los intervalos en cero usan los valores de producción.
func New(data *store.Store, api *cloud.Client) *Syncer {
	return &Syncer{
		Store:          data,
		Cloud:          api,
		DeltaEvery:     30 * time.Second,
		PushEvery:      5 * time.Second,
		HeartbeatEvery: 60 * time.Second,
		Batch:          200,
		Retention:      7 * 24 * time.Hour,
		SkewLimit:      5 * time.Second,
		nudge:          make(chan struct{}, 1),
		reload:         make(chan struct{}, 1),
		pushNow:        make(chan struct{}, 1),
	}
}

// Nudge pide un delta inmediato.
func (s *Syncer) Nudge() {
	select {
	case s.nudge <- struct{}{}:
	default:
	}
}

// PushNow pide vaciar la cola sin esperar el intervalo.
func (s *Syncer) PushNow() {
	select {
	case s.pushNow <- struct{}{}:
	default:
	}
}

// Reload pide un resync desde la versión cero.
func (s *Syncer) Reload() {
	select {
	case s.reload <- struct{}{}:
	default:
	}
	s.Nudge()
}

// Run ejecuta los ciclos hasta que ctx se cancela.
func (s *Syncer) Run(ctx context.Context) {
	if err := s.Pull(ctx, false); err != nil {
		slog.Warn("delta inicial", "error", err)
	}
	_ = s.Push(ctx)
	_ = s.Beat(ctx)
	delta := time.NewTicker(s.DeltaEvery)
	push := time.NewTicker(s.PushEvery)
	beat := time.NewTicker(s.HeartbeatEvery)
	defer delta.Stop()
	defer push.Stop()
	defer beat.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.nudge:
			full := s.takeReload()
			if err := s.Pull(ctx, full); err != nil {
				slog.Warn("delta", "error", err, "completo", full)
			}
		case <-delta.C:
			full := s.takeReload()
			if err := s.Pull(ctx, full); err != nil {
				slog.Warn("delta", "error", err)
			}
		case <-push.C:
			if err := s.Push(ctx); err != nil {
				slog.Warn("envío de marcaciones", "error", err)
			}
		case <-s.pushNow:
			if err := s.Push(ctx); err != nil {
				slog.Warn("envío de marcaciones", "error", err)
			}
		case <-beat.C:
			if err := s.Beat(ctx); err != nil {
				slog.Warn("latido", "error", err)
			}
		}
	}
}

func (s *Syncer) takeReload() bool {
	select {
	case <-s.reload:
		return true
	default:
		return false
	}
}

// Pull aplica páginas hasta ponerse al día. full reemplaza la copia local.
func (s *Syncer) Pull(ctx context.Context, full bool) error {
	since := int64(0)
	var err error
	if !full {
		since, err = s.Store.LastVersion(ctx)
		if err != nil {
			return err
		}
	}
	seen := store.NewSeen()
	var final int64
	for {
		page, err := s.Cloud.Delta(ctx, since)
		if err != nil {
			return err
		}
		s.noteSkew(page.ServerTime)
		var tracked *store.Seen
		if full {
			tracked = &seen
		}
		if err := s.Store.ApplyDelta(ctx, page, tracked); err != nil {
			return err
		}
		final = page.NextSinceVersion
		if !full {
			if err := s.Store.SetLastVersion(ctx, final); err != nil {
				return err
			}
		}
		since = final
		if !page.HasMore {
			break
		}
	}
	if full {
		if err := s.Store.FinishFullSync(ctx, seen); err != nil {
			return err
		}
		if err := s.Store.SetLastVersion(ctx, final); err != nil {
			return err
		}
	}
	if s.OnSynced != nil {
		s.OnSynced()
	}
	return nil
}

// Push sube la cola y las lecturas de enrolamiento pendientes.
func (s *Syncer) Push(ctx context.Context) error {
	if err := s.flushEnrollment(ctx); err != nil {
		slog.Warn("lecturas de enrolamiento", "error", err)
	}
	pending, err := s.Store.PendingLogs(ctx, s.Batch)
	if err != nil {
		return err
	}
	if len(pending) > 0 {
		wire := make([]protocol.Log, 0, len(pending))
		for _, item := range pending {
			wire = append(wire, toWire(item))
		}
		result, err := s.Cloud.PushLogs(ctx, wire)
		if err != nil {
			return err
		}
		s.noteSkew(result.ServerTime)
		ids := append([]string{}, result.Accepted...)
		ids = append(ids, result.Duplicated...)
		for _, rejected := range result.Rejected {
			if rejected.ID != nil {
				slog.Warn("marcación rechazada", "id", *rejected.ID, "reason", rejected.Reason)
				ids = append(ids, *rejected.ID)
			}
		}
		if err := s.Store.MarkLogsSent(ctx, ids, time.Now().UTC()); err != nil {
			return err
		}
	}
	return s.Store.PurgeSent(ctx, time.Now().UTC().Add(-s.Retention))
}

func (s *Syncer) flushEnrollment(ctx context.Context) error {
	pending, err := s.Store.PendingEnrollment(ctx, s.Batch)
	if err != nil {
		return err
	}
	var done []int64
	for _, sample := range pending {
		if err := s.Cloud.ReportEnrollment(ctx, sample); err != nil {
			if len(done) > 0 {
				_ = s.Store.DeleteEnrollment(ctx, done)
			}
			return err
		}
		done = append(done, sample.ID)
	}
	return s.Store.DeleteEnrollment(ctx, done)
}

// Beat envía el latido.
func (s *Syncer) Beat(ctx context.Context) error {
	queue, err := s.Store.QueueSize(ctx)
	if err != nil {
		return err
	}
	version, err := s.Store.LastVersion(ctx)
	if err != nil {
		return err
	}
	listening := []string{}
	if s.Listening != nil {
		listening = s.Listening()
		if listening == nil {
			listening = []string{}
		}
	}
	gatewayUp := false
	if s.GatewayConnected != nil {
		gatewayUp = s.GatewayConnected()
	}
	commandsUp := false
	if s.CommandsConnected != nil {
		commandsUp = s.CommandsConnected()
	}
	server, err := s.Cloud.Heartbeat(ctx, protocol.Heartbeat{
		AgentVersion:      s.Version,
		GatewayConnected:  gatewayUp,
		ListeningDevices:  listening,
		QueueSize:         queue,
		LastVersion:       version,
		CommandsConnected: commandsUp,
		GatewayVersion:    s.GatewayVersion,
	})
	if err != nil {
		return err
	}
	s.noteTime(server)
	return nil
}

func (s *Syncer) noteSkew(value string) {
	server, err := protocol.ParseTime(value)
	if err != nil {
		return
	}
	s.noteTime(server)
}

func (s *Syncer) noteTime(server time.Time) {
	skew := time.Since(server)
	if skew < 0 {
		skew = -skew
	}
	if s.SkewLimit > 0 && skew > s.SkewLimit {
		slog.Warn("reloj desviado respecto de la nube; el sistema debería usar NTP", "deriva", skew.String())
	}
}

func toWire(item store.Log) protocol.Log {
	return protocol.Log{
		ID:           item.ID,
		EmployeeID:   optional(item.EmployeeID),
		CredentialID: optional(item.CredentialID),
		DoorID:       optional(item.DoorID),
		Timestamp:    protocol.FormatTime(item.Timestamp),
		Direction:    item.Direction,
		Status:       item.Status,
		DenialReason: item.DenialReason,
		Method:       item.Method,
		Source:       item.Source,
	}
}

func optional(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}
