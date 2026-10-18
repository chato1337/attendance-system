// Package agent compone el proceso que valida accesos y sincroniza con la nube.
package agent

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"time"

	"attendance-system/edge/internal/cloud"
	"attendance-system/edge/internal/commands"
	"attendance-system/edge/internal/config"
	"attendance-system/edge/internal/engine"
	"attendance-system/edge/internal/gateway"
	"attendance-system/edge/internal/metrics"
	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
	edgesync "attendance-system/edge/internal/sync"
)

// Run bloquea hasta que ctx se cancela o la configuración impide arrancar.
func Run(ctx context.Context, cfg config.Config, version string) error {
	if cfg.APIKey == "" {
		return errors.New("falta api_key")
	}
	data, err := store.Open(cfg.SQLitePath)
	if err != nil {
		return err
	}
	defer func() { _ = data.Close() }()

	collected := metrics.New()
	api := cloud.New(cfg.CloudURL, cfg.APIKey)
	gw := gateway.New(cfg.GatewayURL, gateway.Options{})
	eng := engine.New(data, gw, api, collected)
	syncer := edgesync.New(data, api)
	syncer.DeltaEvery = cfg.DeltaInterval
	syncer.PushEvery = cfg.PushInterval
	syncer.HeartbeatEvery = cfg.HeartbeatInterval
	syncer.Batch = cfg.PushBatchSize
	syncer.Retention = cfg.Retention
	syncer.SkewLimit = cfg.ClockSkewThreshold
	syncer.Version = version
	syncer.GatewayVersion = cfg.GatewayVersion
	syncer.GatewayConnected = gw.Connected
	syncer.Listening = gw.Listening
	syncer.OnSynced = func() {
		devices, err := data.ActiveDevices(context.Background())
		if err != nil {
			slog.Warn("no se pudieron leer los lectores", "error", err)
			return
		}
		gw.SetDevices(devices)
	}

	wsURL, err := commands.WebSocketURL(cfg.CloudURL)
	if err != nil {
		return err
	}
	cmd := commands.New(api, wsURL, func(ctx context.Context, command protocol.Command) map[string]any {
		return dispatch(ctx, command, eng, syncer)
	}, commands.Options{FailuresBeforePoll: cfg.CommandWSFailures})
	syncer.CommandsConnected = cmd.Connected

	if devices, err := data.ActiveDevices(ctx); err == nil {
		gw.SetDevices(devices)
	}

	listener, err := net.Listen("tcp", cfg.ListenAddr)
	if err != nil {
		return err
	}
	server := &http.Server{
		Handler:           routes(data, eng, gw, cmd, collected),
		ReadHeaderTimeout: 5 * time.Second,
	}
	go func() {
		if err := server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("salud local", "error", err)
		}
	}()

	go func() { _ = gw.Run(ctx) }()
	go func() { _ = cmd.Run(ctx) }()
	go syncer.Run(ctx)
	go consume(ctx, cfg, data, eng, gw, syncer)
	go gauges(ctx, data, gw, cmd, collected)

	slog.Info("agente en marcha", "version", version, "cloud", cfg.CloudURL, "gateway", cfg.GatewayURL, "salud", cfg.ListenAddr)
	<-ctx.Done()
	shutdown, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_ = server.Shutdown(shutdown)
	return nil
}

func consume(ctx context.Context, cfg config.Config, data *store.Store, eng *engine.Engine, gw *gateway.Client, syncer *edgesync.Syncer) {
	for {
		select {
		case <-ctx.Done():
			return
		case event := <-gw.Events():
			eng.Handle(ctx, engine.Event{
				Source:   engine.SourceGateway,
				DeviceID: event.DeviceID,
				Raw:      event.Data,
				At:       event.At,
			})
			size, err := data.QueueSize(ctx)
			if err == nil && cfg.QueueThreshold > 0 && size >= cfg.QueueThreshold {
				syncer.PushNow()
			}
		}
	}
}

func gauges(ctx context.Context, data *store.Store, gw *gateway.Client, cmd *commands.Client, collected *metrics.Metrics) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			queue, err := data.QueueSize(ctx)
			if err != nil {
				continue
			}
			version, err := data.LastVersion(ctx)
			if err != nil {
				continue
			}
			collected.SetGauges(queue, gw.Connected(), cmd.Connected(), version)
		}
	}
}
