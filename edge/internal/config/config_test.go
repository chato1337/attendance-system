package config

import "testing"

func TestDefaultGatewayURL(t *testing.T) {
	cfg := Default()
	if cfg.GatewayURL != "ws://127.0.0.1:8080/ws" {
		t.Fatalf("gateway url = %s", cfg.GatewayURL)
	}
}
