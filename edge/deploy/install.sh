#!/bin/sh
# Instala el agente en Linux y, si GATEWAY_BIN está definido, arranca también el gateway externo.
set -eu

prefix="${PREFIX:-/usr/local}"
config_dir="${CONFIG_DIR:-/etc/attendance}"
data_dir="${DATA_DIR:-/var/lib/attendance}"
binary="${AGENT_BIN:-$prefix/bin/attendance-agent}"

install -d -m 0750 "$config_dir" "$data_dir"
install -m 0755 "$(dirname "$0")/../bin/agent" "$binary"

if [ ! -f "$config_dir/agent.yaml" ]; then
  install -m 0640 "$(dirname "$0")/../agent.yaml.example" "$config_dir/agent.yaml"
  echo "Edite $config_dir/agent.yaml y pegue la API key del nodo."
fi

if [ -d /run/systemd/system ]; then
  install -m 0644 "$(dirname "$0")/attendance-agent.service" /etc/systemd/system/attendance-agent.service
  systemctl daemon-reload
  systemctl enable attendance-agent.service
fi

if [ -n "${GATEWAY_BIN:-}" ]; then
  echo "El gateway es un binario aparte. Arranque sugerido, solo en loopback:"
  echo "  $GATEWAY_BIN -addr 127.0.0.1:8080 -http"
fi

echo "Binario en $binary. No publique el puerto del gateway fuera de la máquina."
