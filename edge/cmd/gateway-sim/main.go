package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"attendance-system/edge/internal/gatewaysim"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8080", "dirección de escucha")
	flag.Parse()
	sim, err := gatewaysim.StartAddr(*addr)
	if err != nil {
		log.Fatal(err)
	}
	defer func() { _ = sim.Close() }()
	log.Printf("simulador de gateway en %s", sim.URL)
	log.Printf("inyectar una lectura: curl -s -X POST http://%s/inject -H 'Content-Type: application/json' -d '{\"device_id\":\"COM3\",\"data\":\"AB12\"}'", *addr)
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	<-signals
}
