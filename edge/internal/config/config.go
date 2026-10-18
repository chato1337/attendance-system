package config

type Config struct {
	CloudURL   string
	GatewayURL string
}

func Default() Config {
	return Config{
		CloudURL:   "http://localhost:8000",
		GatewayURL: "ws://127.0.0.1:8080/ws",
	}
}
