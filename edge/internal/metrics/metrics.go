// Package metrics expone la latencia local y el estado del agente en texto Prometheus.
package metrics

import (
	"fmt"
	"strings"
	"sync"
	"time"
)

var buckets = []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1}

// Metrics acumula observaciones del proceso.
type Metrics struct {
	mu          sync.Mutex
	counts      map[string][]uint64
	sums        map[string]float64
	totals      map[string]uint64
	queue       int
	gatewayUp   bool
	commandsUp  bool
	lastVersion int64
}

// New crea un registro vacío.
func New() *Metrics {
	return &Metrics{
		counts: map[string][]uint64{},
		sums:   map[string]float64{},
		totals: map[string]uint64{},
	}
}

// ObserveValidation anota el tiempo hasta decidir (antes de esperar el relé).
func (m *Metrics) ObserveValidation(source string, elapsed time.Duration) {
	if source == "" {
		source = "unknown"
	}
	seconds := elapsed.Seconds()
	m.mu.Lock()
	defer m.mu.Unlock()
	counts := m.counts[source]
	if counts == nil {
		counts = make([]uint64, len(buckets))
	}
	for index, bound := range buckets {
		if seconds <= bound {
			counts[index]++
		}
	}
	m.counts[source] = counts
	m.sums[source] += seconds
	m.totals[source]++
}

// SetGauges actualiza los valores que cambian con el tiempo.
func (m *Metrics) SetGauges(queue int, gatewayUp, commandsUp bool, lastVersion int64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.queue = queue
	m.gatewayUp = gatewayUp
	m.commandsUp = commandsUp
	m.lastVersion = lastVersion
}

// Snapshot copia los totales de un origen para pruebas.
func (m *Metrics) Snapshot(source string) (count uint64, sum float64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.totals[source], m.sums[source]
}

// Render devuelve la exposición Prometheus.
func (m *Metrics) Render() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	var builder strings.Builder
	fmt.Fprintf(&builder, "# HELP edge_queue_size Marcaciones pendientes de envío\n# TYPE edge_queue_size gauge\nedge_queue_size %d\n", m.queue)
	fmt.Fprintf(&builder, "# HELP edge_gateway_connected 1 si el websocket del gateway está abierto\n# TYPE edge_gateway_connected gauge\nedge_gateway_connected %d\n", boolGauge(m.gatewayUp))
	fmt.Fprintf(&builder, "# HELP edge_commands_connected 1 si el canal de comandos está activo\n# TYPE edge_commands_connected gauge\nedge_commands_connected %d\n", boolGauge(m.commandsUp))
	fmt.Fprintf(&builder, "# HELP edge_last_version Cursor de sincronización\n# TYPE edge_last_version gauge\nedge_last_version %d\n", m.lastVersion)
	builder.WriteString("# HELP edge_validation_seconds Tiempo hasta decidir un acceso\n# TYPE edge_validation_seconds histogram\n")
	for source, counts := range m.counts {
		for index, bound := range buckets {
			fmt.Fprintf(&builder, "edge_validation_seconds_bucket{source=%q,le=%q} %d\n", source, trim(bound), counts[index])
		}
		fmt.Fprintf(&builder, "edge_validation_seconds_bucket{source=%q,le=\"+Inf\"} %d\n", source, m.totals[source])
		fmt.Fprintf(&builder, "edge_validation_seconds_sum{source=%q} %g\n", source, m.sums[source])
		fmt.Fprintf(&builder, "edge_validation_seconds_count{source=%q} %d\n", source, m.totals[source])
	}
	return builder.String()
}

func boolGauge(value bool) int {
	if value {
		return 1
	}
	return 0
}

func trim(value float64) string {
	return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%.3f", value), "0"), ".")
}
