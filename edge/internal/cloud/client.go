// Package cloud es el cliente HTTP del protocolo Edge v1.
package cloud

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"attendance-system/edge/internal/protocol"
	"attendance-system/edge/internal/store"
)

const (
	maxAttempts = 4
	deltaLimit  = 500
)

// Client llama a la nube con la API key del nodo.
type Client struct {
	baseURL string
	apiKey  string
	http    *http.Client
}

// New crea el cliente. baseURL es el origen de la API, sin /api/v1.
func New(baseURL, apiKey string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		http:    &http.Client{Timeout: 40 * time.Second},
	}
}

// Token devuelve la API key para el primer mensaje del WebSocket.
func (c *Client) Token() string {
	if c == nil {
		return ""
	}
	return c.apiKey
}

// Delta pide una página de cambios.
func (c *Client) Delta(ctx context.Context, since int64) (protocol.Delta, error) {
	query := url.Values{}
	query.Set("since_version", strconv.FormatInt(since, 10))
	query.Set("limit", strconv.Itoa(deltaLimit))
	var page protocol.Delta
	err := c.do(ctx, http.MethodGet, "/api/v1/edge/sync/delta/", query, nil, &page)
	return page, err
}

// PushLogs envía un lote. El contrato es idempotente por el id de cada marcación.
func (c *Client) PushLogs(ctx context.Context, logs []protocol.Log) (protocol.BatchResult, error) {
	var result protocol.BatchResult
	err := c.do(ctx, http.MethodPost, "/api/v1/edge/logs/batch/", nil, map[string]any{"logs": logs}, &result)
	return result, err
}

// Heartbeat informa el estado del nodo y devuelve la hora del servidor.
func (c *Client) Heartbeat(ctx context.Context, beat protocol.Heartbeat) (time.Time, error) {
	var timed protocol.Timed
	if err := c.do(ctx, http.MethodPost, "/api/v1/edge/heartbeat/", nil, beat, &timed); err != nil {
		return time.Time{}, err
	}
	return protocol.ParseTime(timed.ServerTime)
}

// Poll espera comandos pendientes.
func (c *Client) Poll(ctx context.Context, waitSeconds int) (protocol.Poll, error) {
	query := url.Values{}
	query.Set("wait", strconv.Itoa(waitSeconds))
	var page protocol.Poll
	err := c.do(ctx, http.MethodGet, "/api/v1/edge/commands/", query, nil, &page)
	return page, err
}

// Ack confirma un comando. Un segundo ack no cambia el resultado guardado.
func (c *Client) Ack(ctx context.Context, id string, result map[string]any) error {
	path := "/api/v1/edge/commands/" + url.PathEscape(id) + "/ack/"
	return c.do(ctx, http.MethodPost, path, nil, map[string]any{"result": result}, nil)
}

// ReportEnrollment publica una lectura del modo asistido.
func (c *Client) ReportEnrollment(ctx context.Context, sample store.EnrollmentSample) error {
	body := protocol.EnrollmentRead{
		ReaderID: sample.ReaderID, CommandID: sample.CommandID, Raw: sample.Raw,
		Payload: sample.Payload, CredentialType: sample.CredentialType, Error: sample.Error,
	}
	return c.do(ctx, http.MethodPost, "/api/v1/edge/enrollment-reads/", nil, body, nil)
}

func (c *Client) do(ctx context.Context, method, path string, query url.Values, body any, out any) error {
	var payload []byte
	var err error
	if body != nil {
		payload, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	endpoint := c.baseURL + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	var last error
	for attempt := 0; attempt < maxAttempts; attempt++ {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		last = c.once(ctx, method, endpoint, payload, out)
		if last == nil || !retryable(last) {
			return last
		}
		delay := time.Duration(attempt+1) * 200 * time.Millisecond
		if status, ok := last.(*statusError); ok && status.retryAfter > 0 {
			delay = status.retryAfter
		}
		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
	return last
}

func (c *Client) once(ctx context.Context, method, endpoint string, payload []byte, out any) error {
	var reader io.Reader
	if payload != nil {
		reader = bytes.NewReader(payload)
	}
	request, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", "Bearer "+c.apiKey)
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := c.http.Do(request)
	if err != nil {
		return err
	}
	defer func() { _ = response.Body.Close() }()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	if err != nil {
		return err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return &statusError{code: response.StatusCode, body: string(responseBody), retryAfter: retryAfter(response)}
	}
	if out == nil || len(responseBody) == 0 {
		return nil
	}
	if err := json.Unmarshal(responseBody, out); err != nil {
		return fmt.Errorf("respuesta json: %w", err)
	}
	return nil
}

type statusError struct {
	code       int
	body       string
	retryAfter time.Duration
}

func (e *statusError) Error() string {
	return fmt.Sprintf("nube respondió %d: %s", e.code, trim(e.body))
}

func retryable(err error) bool {
	status, ok := err.(*statusError)
	if !ok {
		return true
	}
	return status.code == http.StatusTooManyRequests || status.code >= 500
}

func retryAfter(response *http.Response) time.Duration {
	value := response.Header.Get("Retry-After")
	if value == "" {
		return 0
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds < 0 {
		return 0
	}
	return time.Duration(seconds) * time.Second
}

func trim(value string) string {
	value = strings.TrimSpace(value)
	if len(value) > 180 {
		return value[:180]
	}
	return value
}
