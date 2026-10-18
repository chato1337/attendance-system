package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultGatewayURL(t *testing.T) {
	cfg := Default()
	if cfg.GatewayURL != "ws://127.0.0.1:8080/ws" {
		t.Fatalf("gateway url = %s", cfg.GatewayURL)
	}
}

func TestEnvOverridesFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agent.yaml")
	if err := os.WriteFile(path, []byte("cloud_url: http://archivo\napi_key: desde-archivo\ndelta_interval: 10s\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("EDGE_CLOUD_URL", "http://entorno")
	t.Setenv("EDGE_API_KEY", "")
	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.CloudURL != "http://entorno" || cfg.APIKey != "desde-archivo" || cfg.DeltaInterval.Seconds() != 10 {
		t.Fatalf("%+v", cfg)
	}
}
