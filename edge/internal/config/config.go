// Package config carga agent.yaml y deja que el entorno lo pise.
package config

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

// Config es la configuración efectiva del agente.
type Config struct {
	CloudURL           string
	APIKey             string
	GatewayURL         string
	SQLitePath         string
	DeltaInterval      time.Duration
	PushInterval       time.Duration
	HeartbeatInterval  time.Duration
	PushBatchSize      int
	QueueThreshold     int
	Retention          time.Duration
	ListenAddr         string
	ClockSkewThreshold time.Duration
	CommandWSFailures  int
	GatewayVersion     string
}

type fileConfig struct {
	CloudURL           string `yaml:"cloud_url"`
	APIKey             string `yaml:"api_key"`
	GatewayURL         string `yaml:"gateway_url"`
	SQLitePath         string `yaml:"sqlite_path"`
	DeltaInterval      string `yaml:"delta_interval"`
	PushInterval       string `yaml:"push_interval"`
	HeartbeatInterval  string `yaml:"heartbeat_interval"`
	PushBatchSize      int    `yaml:"push_batch_size"`
	QueueThreshold     int    `yaml:"queue_threshold"`
	Retention          string `yaml:"retention"`
	ListenAddr         string `yaml:"listen_addr"`
	ClockSkewThreshold string `yaml:"clock_skew_threshold"`
	CommandWSFailures  int    `yaml:"command_ws_failures"`
	GatewayVersion     string `yaml:"gateway_version"`
}

// Default devuelve los valores de un puesto de desarrollo.
func Default() Config {
	return Config{
		CloudURL:           "http://localhost:8000",
		GatewayURL:         "ws://127.0.0.1:8080/ws",
		SQLitePath:         "agent.db",
		DeltaInterval:      30 * time.Second,
		PushInterval:       5 * time.Second,
		HeartbeatInterval:  60 * time.Second,
		PushBatchSize:      200,
		QueueThreshold:     50,
		Retention:          7 * 24 * time.Hour,
		ListenAddr:         "127.0.0.1:9090",
		ClockSkewThreshold: 5 * time.Second,
		CommandWSFailures:  3,
	}
}

// Load lee un YAML opcional y aplica las variables EDGE_*.
func Load(path string) (Config, error) {
	cfg := Default()
	if path != "" {
		raw, err := os.ReadFile(path)
		if err != nil {
			return Config{}, fmt.Errorf("leer configuración: %w", err)
		}
		var file fileConfig
		if err := yaml.Unmarshal(raw, &file); err != nil {
			return Config{}, fmt.Errorf("interpretar configuración: %w", err)
		}
		if err := cfg.apply(file); err != nil {
			return Config{}, err
		}
	}
	cfg.applyEnv()
	return cfg, nil
}

func (cfg *Config) apply(file fileConfig) error {
	setString(&cfg.CloudURL, file.CloudURL)
	setString(&cfg.APIKey, file.APIKey)
	setString(&cfg.GatewayURL, file.GatewayURL)
	setString(&cfg.SQLitePath, file.SQLitePath)
	setString(&cfg.ListenAddr, file.ListenAddr)
	setString(&cfg.GatewayVersion, file.GatewayVersion)
	if file.PushBatchSize > 0 {
		cfg.PushBatchSize = file.PushBatchSize
	}
	if file.QueueThreshold > 0 {
		cfg.QueueThreshold = file.QueueThreshold
	}
	if file.CommandWSFailures > 0 {
		cfg.CommandWSFailures = file.CommandWSFailures
	}
	var err error
	if cfg.DeltaInterval, err = parseDuration(file.DeltaInterval, cfg.DeltaInterval); err != nil {
		return fmt.Errorf("delta_interval: %w", err)
	}
	if cfg.PushInterval, err = parseDuration(file.PushInterval, cfg.PushInterval); err != nil {
		return fmt.Errorf("push_interval: %w", err)
	}
	if cfg.HeartbeatInterval, err = parseDuration(file.HeartbeatInterval, cfg.HeartbeatInterval); err != nil {
		return fmt.Errorf("heartbeat_interval: %w", err)
	}
	if cfg.Retention, err = parseDuration(file.Retention, cfg.Retention); err != nil {
		return fmt.Errorf("retention: %w", err)
	}
	if cfg.ClockSkewThreshold, err = parseDuration(file.ClockSkewThreshold, cfg.ClockSkewThreshold); err != nil {
		return fmt.Errorf("clock_skew_threshold: %w", err)
	}
	return nil
}

func (cfg *Config) applyEnv() {
	setString(&cfg.CloudURL, os.Getenv("EDGE_CLOUD_URL"))
	setString(&cfg.APIKey, os.Getenv("EDGE_API_KEY"))
	setString(&cfg.GatewayURL, os.Getenv("EDGE_GATEWAY_URL"))
	setString(&cfg.SQLitePath, os.Getenv("EDGE_SQLITE_PATH"))
	setString(&cfg.ListenAddr, os.Getenv("EDGE_LISTEN_ADDR"))
}

func setString(target *string, value string) {
	if value != "" {
		*target = value
	}
}

func parseDuration(value string, fallback time.Duration) (time.Duration, error) {
	if value == "" {
		return fallback, nil
	}
	return time.ParseDuration(value)
}
