package engine

import (
	"context"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"attendance-system/edge/internal/profile"
	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
)

type fakeRelay struct {
	devices []string
	err     error
}

func (f *fakeRelay) Open(_ context.Context, deviceID string) error {
	f.devices = append(f.devices, deviceID)
	return f.err
}

type fakeReporter struct {
	samples []store.EnrollmentSample
}

func (f *fakeReporter) ReportEnrollment(_ context.Context, sample store.EnrollmentSample) error {
	f.samples = append(f.samples, sample)
	return nil
}

func TestAccessDecisions(t *testing.T) {
	now := time.Date(2026, 10, 18, 12, 0, 0, 0, time.UTC)
	past := now.Add(-time.Hour).Format(time.RFC3339)
	future := now.Add(time.Hour).Format(time.RFC3339)
	cases := []struct {
		name        string
		mutate      func(*protocol.Delta)
		event       Event
		status      string
		reason      string
		opened      bool
		inside      bool
		startInside bool
	}{
		{
			name:   "entrada concedida",
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: " ab12 ", At: now},
			status: StatusGranted, opened: true, inside: true,
		},
		{
			name: "salida concedida",
			mutate: func(page *protocol.Delta) {
				page.Doors[0].Direction = "OUT"
			},
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status: StatusGranted, opened: true, inside: false,
		},
		{
			name:   "dispositivo desconocido",
			event:  Event{Source: SourceGateway, DeviceID: "COM9", Raw: "ab12", At: now},
			status: StatusDenied, reason: "UNKNOWN_DEVICE",
		},
		{
			name:   "lectura mal formada",
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "????", At: now},
			status: StatusDenied, reason: "MALFORMED_READ",
		},
		{
			name:   "credencial desconocida",
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "00cd", At: now},
			status: StatusDenied, reason: "UNKNOWN_CREDENTIAL",
		},
		{
			name: "credencial inactiva",
			mutate: func(page *protocol.Delta) {
				page.Credentials[0].IsActive = false
			},
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status: StatusDenied, reason: "INACTIVE",
		},
		{
			name: "empleado inactivo",
			mutate: func(page *protocol.Delta) {
				page.Employees[0].IsActive = false
			},
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status: StatusDenied, reason: "INACTIVE",
		},
		{
			name: "credencial vencida",
			mutate: func(page *protocol.Delta) {
				page.Credentials[0].ValidUntil = &past
			},
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status: StatusDenied, reason: "EXPIRED",
		},
		{
			name: "credencial aún no vigente",
			mutate: func(page *protocol.Delta) {
				page.Credentials[0].ValidFrom = &future
			},
			event:  Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status: StatusDenied, reason: "EXPIRED",
		},
		{
			name: "anti-passback duro",
			mutate: func(page *protocol.Delta) {
				page.Doors[0].ApbMode = "HARD"
			},
			startInside: true,
			event:       Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status:      StatusDenied, reason: "APB_VIOLATION", inside: true,
		},
		{
			name: "anti-passback blando abre y marca",
			mutate: func(page *protocol.Delta) {
				page.Doors[0].ApbMode = "SOFT"
			},
			startInside: true,
			event:       Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now},
			status:      StatusGranted, reason: "APB_VIOLATION", opened: true, inside: true,
		},
		{
			name:   "rostro no habilitado",
			event:  Event{Source: SourceCloud, DoorID: "door", Type: "FACIAL", Payload: "face-user", At: now},
			status: StatusDenied, reason: "FACE_NOT_ALLOWED",
		},
		{
			name: "rostro concedido",
			mutate: func(page *protocol.Delta) {
				page.Doors[0].FaceEnabled = true
				page.Credentials = append(page.Credentials, protocol.Credential{
					ID: "face", EmployeeID: "emp", Type: "FACIAL", Payload: "face-user", IsActive: true, Version: 6,
				})
			},
			event:  Event{Source: SourceCloud, DoorID: "door", Type: "FACIAL", Payload: "face-user", At: now},
			status: StatusGranted, opened: true, inside: true,
		},
	}
	for _, item := range cases {
		t.Run(item.name, func(t *testing.T) {
			data := base(t)
			if item.mutate != nil {
				page := basePage()
				item.mutate(&page)
				if err := data.ApplyDelta(context.Background(), page, nil); err != nil {
					t.Fatal(err)
				}
			}
			if item.startInside {
				if err := data.SaveState(context.Background(), "emp", true, now); err != nil {
					t.Fatal(err)
				}
			}
			relay := &fakeRelay{}
			eng := New(data, relay, nil, nil)
			result := eng.Handle(context.Background(), item.event)
			if result.Status != item.status || result.DenialReason != item.reason || result.Opened != item.opened {
				t.Fatalf("resultado %+v", result)
			}
			if item.opened && len(relay.devices) != 1 {
				t.Fatalf("relé = %v", relay.devices)
			}
			if item.status == StatusGranted || item.reason == "APB_VIOLATION" {
				inside, err := data.State(context.Background(), "emp")
				if err != nil {
					t.Fatal(err)
				}
				if inside != item.inside {
					t.Fatalf("dentro = %v", inside)
				}
			}
		})
	}
}

func TestChangingProfileDoesNotRequireRestart(t *testing.T) {
	data := base(t)
	eng := New(data, &fakeRelay{}, nil, nil)
	ctx := context.Background()
	now := time.Now().UTC()
	denied := eng.Handle(ctx, Event{Source: SourceGateway, DeviceID: "COM3", Raw: "0000000123", At: now})
	if denied.DenialReason != "MALFORMED_READ" && denied.DenialReason != "UNKNOWN_CREDENTIAL" {
		t.Fatalf("lectura decimal con perfil hex: %+v", denied)
	}
	page := basePage()
	page.ReaderProfiles[0].Normalization = []profile.Step{
		{Op: "trim"},
		{Op: "regex_extract", Pattern: "([0-9]+)"},
		{Op: "strip_leading_zeros"},
		{Op: "pad_left", Length: 10, Char: "0"},
	}
	page.ReaderProfiles[0].MinLength = 10
	page.ReaderProfiles[0].MaxLength = 10
	page.ReaderProfiles[0].Version = 20
	page.Credentials[0].Payload = "0000000123"
	page.Credentials[0].Version = 21
	if err := data.ApplyDelta(ctx, page, nil); err != nil {
		t.Fatal(err)
	}
	granted := eng.Handle(ctx, Event{Source: SourceGateway, DeviceID: "COM3", Raw: "0000000123", At: now})
	if granted.Status != StatusGranted || !granted.Opened {
		t.Fatalf("tras cambiar el perfil: %+v", granted)
	}
}

func TestEnrollmentCapturesWithoutOpening(t *testing.T) {
	data := base(t)
	relay := &fakeRelay{}
	reporter := &fakeReporter{}
	eng := New(data, relay, reporter, nil)
	ctx := context.Background()
	if err := eng.ArmEnrollment(ctx, "reader", "cmd", 30); err != nil {
		t.Fatal(err)
	}
	result := eng.Handle(ctx, Event{Source: SourceGateway, DeviceID: "COM3", Raw: " ab12 ", At: time.Now().UTC()})
	if result.Status != StatusEnrollment {
		t.Fatalf("estado %s", result.Status)
	}
	if len(relay.devices) != 0 || len(reporter.samples) != 1 || reporter.samples[0].Payload != "0000AB12" {
		t.Fatalf("relé %v lecturas %+v", relay.devices, reporter.samples)
	}
	pending, err := data.PendingLogs(ctx, 10)
	if err != nil || len(pending) != 0 {
		t.Fatalf("no debía haber marcación: %d %v", len(pending), err)
	}
}

func TestRemoteOpen(t *testing.T) {
	data := base(t)
	relay := &fakeRelay{}
	eng := New(data, relay, nil, nil)
	result := eng.RemoteOpen(context.Background(), "door", "visita", "ana")
	if result.Status != StatusGranted || !result.Opened || result.Method != "REMOTE" {
		t.Fatalf("%+v", result)
	}
	missing := eng.RemoteOpen(context.Background(), "nope", "visita", "ana")
	if missing.Status != StatusFailed {
		t.Fatalf("%+v", missing)
	}
}

func TestValidationP95StaysUnderBudget(t *testing.T) {
	data := base(t)
	eng := New(data, &fakeRelay{}, nil, nil)
	ctx := context.Background()
	now := time.Now().UTC()
	samples := make([]time.Duration, 0, 200)
	for range 200 {
		result := eng.Handle(ctx, Event{Source: SourceGateway, DeviceID: "COM3", Raw: "ab12", At: now})
		if result.Status != StatusGranted && result.DenialReason != "APB_VIOLATION" {
			t.Fatalf("%+v", result)
		}
		samples = append(samples, result.Validation)
		now = now.Add(time.Second)
	}
	sort.Slice(samples, func(i, j int) bool { return samples[i] < samples[j] })
	p95 := samples[len(samples)*95/100]
	if p95 > 200*time.Millisecond {
		t.Fatalf("p95 = %s", p95)
	}
}

func base(t *testing.T) *store.Store {
	t.Helper()
	data, err := store.Open(filepath.Join(t.TempDir(), "agent.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = data.Close() })
	if err := data.ApplyDelta(context.Background(), basePage(), nil); err != nil {
		t.Fatal(err)
	}
	return data
}

func basePage() protocol.Delta {
	return protocol.Delta{
		ReaderProfiles: []protocol.ReaderProfile{{
			ID: "profile", Name: "hex", CredentialType: "RFID",
			Normalization: []profile.Step{
				{Op: "trim"}, {Op: "upper"},
				{Op: "regex_extract", Pattern: "([0-9A-F]+)"},
				{Op: "pad_left", Length: 8, Char: "0"},
			},
			MinLength: 8, MaxLength: 8, IsActive: true, Version: 1,
		}},
		Employees: []protocol.Employee{{
			ID: "emp", DocumentID: "1", FirstName: "Ada", LastName: "Lovelace", IsActive: true, Version: 2,
		}},
		Credentials: []protocol.Credential{{
			ID: "cred", EmployeeID: "emp", Type: "RFID", Payload: "0000AB12", IsActive: true, Version: 3,
		}},
		Doors: []protocol.Door{{
			ID: "door", Name: "Principal", RelayDeviceID: "RELAY1", Direction: "IN", ApbMode: "OFF", IsActive: true, Version: 4,
		}},
		Readers: []protocol.Reader{{
			ID: "reader", DoorID: "door", ReaderProfileID: "profile", Name: "Lector", ReaderDeviceID: "COM3", IsActive: true, Version: 5,
		}},
	}
}
