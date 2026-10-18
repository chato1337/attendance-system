package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"attendance-system/edge/internal/agent"
	"attendance-system/edge/internal/config"
)

// Version se informa en el latido y con -version.
const Version = "0.3.0"

func main() {
	configPath := flag.String("config", "", "ruta de agent.yaml")
	showVersion := flag.Bool("version", false, "muestra la versión del agente")
	flag.Parse()
	if *showVersion {
		fmt.Println(Version)
		return
	}
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	cfg, err := config.Load(*configPath)
	if err != nil {
		slog.Error("configuración", "error", err)
		os.Exit(1)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := agent.Run(ctx, cfg, Version); err != nil {
		slog.Error("agente", "error", err)
		os.Exit(1)
	}
}
