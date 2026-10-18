package main

import (
	"flag"
	"fmt"
)

const Version = "0.1.0"

func main() {
	showVersion := flag.Bool("version", false, "muestra la versión del agente")
	flag.Parse()
	if *showVersion {
		fmt.Println(Version)
		return
	}
	fmt.Println("attendance-edge: hello")
}
