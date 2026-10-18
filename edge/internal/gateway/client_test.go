package gateway

import (
	"context"
	"testing"
	"time"

	"attendance-system/edge/internal/gatewaysim"
)

func TestReplayIsIgnoredAndLiveReadOpens(t *testing.T) {
	sim, err := gatewaysim.Start()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = sim.Close() })
	sim.SetHistory([]gatewaysim.Frame{{Event: "hardware_read", DeviceID: "COM3", Data: "VIEJA"}})
	client := New(sim.URL, Options{MinBackoff: 20 * time.Millisecond, MaxBackoff: 50 * time.Millisecond, OpenTimeout: time.Second})
	client.SetDevices([]string{"COM3"})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = client.Run(ctx) }()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if contains(sim.Listened(), "COM3") {
			break
		}
		time.Sleep(15 * time.Millisecond)
	}
	if !contains(sim.Listened(), "COM3") {
		t.Fatal("el agente no pidió listen")
	}
	sim.Inject("COM3", "AB12")
	select {
	case event := <-client.Events():
		if event.Data != "AB12" {
			t.Fatalf("lectura %q", event.Data)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no llegó la lectura en vivo")
	}
	select {
	case event := <-client.Events():
		t.Fatalf("se procesó el historial: %+v", event)
	case <-time.After(80 * time.Millisecond):
	}
	openCtx, openCancel := context.WithTimeout(context.Background(), time.Second)
	defer openCancel()
	if err := client.Open(openCtx, "RELAY1"); err != nil {
		t.Fatal(err)
	}
}

func TestOpenReportsGatewayError(t *testing.T) {
	sim, err := gatewaysim.Start()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = sim.Close() })
	sim.FailOpen("RELAY1", "puerto ausente")
	client := New(sim.URL, Options{MinBackoff: 20 * time.Millisecond, MaxBackoff: 40 * time.Millisecond, OpenTimeout: time.Second})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = client.Run(ctx) }()
	waitUntil(t, client.Ready)
	if err := client.Open(context.Background(), "RELAY1"); err == nil {
		t.Fatal("se esperaba el error del gateway")
	}
}

func waitUntil(t *testing.T, ready func() bool) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if ready() {
			return
		}
		time.Sleep(15 * time.Millisecond)
	}
	t.Fatal("timeout")
}

func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
