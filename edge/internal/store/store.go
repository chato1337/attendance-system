// Package store guarda la copia local del agente en SQLite.
package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"attendance-system/edge/internal/profile"
	"attendance-system/edge/internal/protocol"

	_ "modernc.org/sqlite"
)

const schema = `
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    department_id TEXT,
    is_active INTEGER NOT NULL,
    cloud_inside INTEGER NOT NULL,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS credentials_lookup ON credentials(type, payload);
CREATE TABLE IF NOT EXISTS reader_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    normalization TEXT NOT NULL,
    min_length INTEGER NOT NULL,
    max_length INTEGER NOT NULL,
    is_active INTEGER NOT NULL,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS doors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    relay_device_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    apb_mode TEXT NOT NULL,
    face_enabled INTEGER NOT NULL,
    is_active INTEGER NOT NULL,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS readers (
    id TEXT PRIMARY KEY,
    door_id TEXT NOT NULL,
    reader_profile_id TEXT NOT NULL,
    name TEXT NOT NULL,
    reader_device_id TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS employee_state (
    employee_id TEXT PRIMARY KEY,
    is_inside INTEGER NOT NULL,
    last_event_at TEXT
);
CREATE TABLE IF NOT EXISTS log_queue (
    id TEXT PRIMARY KEY,
    employee_id TEXT,
    credential_id TEXT,
    door_id TEXT,
    timestamp TEXT NOT NULL,
    direction TEXT NOT NULL,
    status TEXT NOT NULL,
    denial_reason TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '',
    sent_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollment_windows (
    reader_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL,
    until_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollment_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reader_id TEXT NOT NULL,
    command_id TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    credential_type TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
`

// Store es la base local del agente.
type Store struct {
	db *sql.DB
}

// Log es una marcación todavía no confirmada por la nube, o ya enviada.
type Log struct {
	ID           string
	EmployeeID   string
	CredentialID string
	DoorID       string
	Timestamp    time.Time
	Direction    string
	Status       string
	DenialReason string
	Method       string
	Source       string
	Raw          string
}

// Credential es una credencial local.
type Credential struct {
	ID         string
	EmployeeID string
	Type       string
	Payload    string
	IsActive   bool
	ValidFrom  *time.Time
	ValidUntil *time.Time
}

// Door es una puerta local.
type Door struct {
	ID            string
	Name          string
	RelayDeviceID string
	Direction     string
	ApbMode       string
	FaceEnabled   bool
	IsActive      bool
}

// ReaderView junta el lector, su puerta y su perfil.
type ReaderView struct {
	ReaderID       string
	DeviceID       string
	ReaderActive   bool
	Door           Door
	ProfileID      string
	CredentialType string
	Steps          []profile.Step
	MinLength      int
	MaxLength      int
	ProfileActive  bool
}

// EnrollmentSample es una lectura del modo de enrolamiento.
type EnrollmentSample struct {
	ID             int64
	ReaderID       string
	CommandID      string
	Raw            string
	Payload        string
	CredentialType string
	Error          string
	CreatedAt      time.Time
}

// Seen acumula los ids vistos durante un resync completo.
type Seen struct {
	Employees   map[string]struct{}
	Credentials map[string]struct{}
	Profiles    map[string]struct{}
	Doors       map[string]struct{}
	Readers     map[string]struct{}
}

// NewSeen crea un conjunto vacío para un reload.
func NewSeen() Seen {
	return Seen{
		Employees:   map[string]struct{}{},
		Credentials: map[string]struct{}{},
		Profiles:    map[string]struct{}{},
		Doors:       map[string]struct{}{},
		Readers:     map[string]struct{}{},
	}
}

// Open abre (y crea) la base en path.
func Open(path string) (*Store, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return nil, fmt.Errorf("crear directorio de sqlite: %w", err)
	}
	dsn := "file:" + filepath.ToSlash(path) + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("abrir sqlite: %w", err)
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	store := &Store{db: db}
	for _, statement := range strings.Split(schema, ";") {
		statement = strings.TrimSpace(statement)
		if statement == "" {
			continue
		}
		if _, err := db.Exec(statement); err != nil {
			_ = db.Close()
			return nil, fmt.Errorf("crear esquema: %w", err)
		}
	}
	return store, nil
}

// Close cierra la base.
func (s *Store) Close() error {
	return s.db.Close()
}

// ApplyDelta inserta o actualiza una página. No borra filas ausentes.
func (s *Store) ApplyDelta(ctx context.Context, page protocol.Delta, seen *Seen) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	for _, item := range page.ReaderProfiles {
		if err := upsertProfile(ctx, tx, item); err != nil {
			return err
		}
		if seen != nil {
			seen.Profiles[item.ID] = struct{}{}
		}
	}
	for _, item := range page.Employees {
		if err := upsertEmployee(ctx, tx, item); err != nil {
			return err
		}
		if seen != nil {
			seen.Employees[item.ID] = struct{}{}
		}
	}
	for _, item := range page.Credentials {
		if err := upsertCredential(ctx, tx, item); err != nil {
			return err
		}
		if seen != nil {
			seen.Credentials[item.ID] = struct{}{}
		}
	}
	for _, item := range page.Doors {
		if err := upsertDoor(ctx, tx, item); err != nil {
			return err
		}
		if seen != nil {
			seen.Doors[item.ID] = struct{}{}
		}
	}
	for _, item := range page.Readers {
		if err := upsertReader(ctx, tx, item); err != nil {
			return err
		}
		if seen != nil {
			seen.Readers[item.ID] = struct{}{}
		}
	}
	return tx.Commit()
}

// FinishFullSync borra lo que un reload completo ya no entregó.
func (s *Store) FinishFullSync(ctx context.Context, seen Seen) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if err := deleteMissing(ctx, tx, "reader_profiles", seen.Profiles); err != nil {
		return err
	}
	if err := deleteMissing(ctx, tx, "employees", seen.Employees); err != nil {
		return err
	}
	if err := deleteMissing(ctx, tx, "credentials", seen.Credentials); err != nil {
		return err
	}
	if err := deleteMissing(ctx, tx, "doors", seen.Doors); err != nil {
		return err
	}
	if err := deleteMissing(ctx, tx, "readers", seen.Readers); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `
		DELETE FROM employee_state
		WHERE employee_id NOT IN (SELECT id FROM employees)
	`); err != nil {
		return err
	}
	return tx.Commit()
}

func deleteMissing(ctx context.Context, tx *sql.Tx, table string, seen map[string]struct{}) error {
	rows, err := tx.QueryContext(ctx, "SELECT id FROM "+table)
	if err != nil {
		return err
	}
	var stale []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			_ = rows.Close()
			return err
		}
		if _, ok := seen[id]; !ok {
			stale = append(stale, id)
		}
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return err
	}
	if err := rows.Close(); err != nil {
		return err
	}
	for _, id := range stale {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+table+" WHERE id = ?", id); err != nil {
			return err
		}
	}
	return nil
}

func upsertProfile(ctx context.Context, tx *sql.Tx, item protocol.ReaderProfile) error {
	raw, err := json.Marshal(item.Normalization)
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `
		INSERT INTO reader_profiles
			(id, name, credential_type, normalization, min_length, max_length, is_active, version)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			name = excluded.name,
			credential_type = excluded.credential_type,
			normalization = excluded.normalization,
			min_length = excluded.min_length,
			max_length = excluded.max_length,
			is_active = excluded.is_active,
			version = excluded.version
	`, item.ID, item.Name, item.CredentialType, string(raw), item.MinLength, item.MaxLength, boolInt(item.IsActive), item.Version)
	return err
}

func upsertEmployee(ctx context.Context, tx *sql.Tx, item protocol.Employee) error {
	var department any
	if item.DepartmentID != nil {
		department = *item.DepartmentID
	}
	if _, err := tx.ExecContext(ctx, `
		INSERT INTO employees
			(id, document_id, first_name, last_name, department_id, is_active, cloud_inside, version)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			document_id = excluded.document_id,
			first_name = excluded.first_name,
			last_name = excluded.last_name,
			department_id = excluded.department_id,
			is_active = excluded.is_active,
			cloud_inside = excluded.cloud_inside,
			version = excluded.version
	`, item.ID, item.DocumentID, item.FirstName, item.LastName, department, boolInt(item.IsActive), boolInt(item.IsInside), item.Version); err != nil {
		return err
	}
	_, err := tx.ExecContext(ctx, `
		INSERT INTO employee_state (employee_id, is_inside, last_event_at)
		VALUES (?, ?, NULL)
		ON CONFLICT(employee_id) DO NOTHING
	`, item.ID, boolInt(item.IsInside))
	return err
}

func upsertCredential(ctx context.Context, tx *sql.Tx, item protocol.Credential) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO credentials
			(id, employee_id, type, payload, is_active, valid_from, valid_until, version)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			employee_id = excluded.employee_id,
			type = excluded.type,
			payload = excluded.payload,
			is_active = excluded.is_active,
			valid_from = excluded.valid_from,
			valid_until = excluded.valid_until,
			version = excluded.version
	`, item.ID, item.EmployeeID, item.Type, item.Payload, boolInt(item.IsActive), nullableTime(item.ValidFrom), nullableTime(item.ValidUntil), item.Version)
	return err
}

func upsertDoor(ctx context.Context, tx *sql.Tx, item protocol.Door) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO doors
			(id, name, relay_device_id, direction, apb_mode, face_enabled, is_active, version)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			name = excluded.name,
			relay_device_id = excluded.relay_device_id,
			direction = excluded.direction,
			apb_mode = excluded.apb_mode,
			face_enabled = excluded.face_enabled,
			is_active = excluded.is_active,
			version = excluded.version
	`, item.ID, item.Name, item.RelayDeviceID, item.Direction, item.ApbMode, boolInt(item.FaceEnabled), boolInt(item.IsActive), item.Version)
	return err
}

func upsertReader(ctx context.Context, tx *sql.Tx, item protocol.Reader) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO readers (id, door_id, reader_profile_id, name, reader_device_id, is_active, version)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			door_id = excluded.door_id,
			reader_profile_id = excluded.reader_profile_id,
			name = excluded.name,
			reader_device_id = excluded.reader_device_id,
			is_active = excluded.is_active,
			version = excluded.version
	`, item.ID, item.DoorID, item.ReaderProfileID, item.Name, item.ReaderDeviceID, boolInt(item.IsActive), item.Version)
	return err
}

func nullableTime(value *string) any {
	if value == nil || strings.TrimSpace(*value) == "" {
		return nil
	}
	return *value
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

// LastVersion devuelve el cursor local.
func (s *Store) LastVersion(ctx context.Context) (int64, error) {
	var raw string
	err := s.db.QueryRowContext(ctx, `SELECT value FROM meta WHERE key = 'last_version'`).Scan(&raw)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	var version int64
	if _, err := fmt.Sscan(raw, &version); err != nil {
		return 0, err
	}
	return version, nil
}

// SetLastVersion guarda el cursor local.
func (s *Store) SetLastVersion(ctx context.Context, version int64) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO meta (key, value) VALUES ('last_version', ?)
		ON CONFLICT(key) DO UPDATE SET value = excluded.value
	`, fmt.Sprintf("%d", version))
	return err
}

// QueueSize cuenta marcaciones pendientes.
func (s *Store) QueueSize(ctx context.Context) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM log_queue WHERE sent_at IS NULL`).Scan(&count)
	return count, err
}

// EnqueueLog agrega una marcación. Repetir el mismo id no crea otra fila.
func (s *Store) EnqueueLog(ctx context.Context, item Log) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO log_queue
			(id, employee_id, credential_id, door_id, timestamp, direction, status, denial_reason, method, source, raw, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO NOTHING
	`, item.ID, emptyNull(item.EmployeeID), emptyNull(item.CredentialID), emptyNull(item.DoorID),
		protocol.FormatTime(item.Timestamp), item.Direction, item.Status, item.DenialReason, item.Method, item.Source, item.Raw,
		protocol.FormatTime(time.Now()))
	return err
}

func emptyNull(value string) any {
	if value == "" {
		return nil
	}
	return value
}

// PendingLogs devuelve marcaciones aún no confirmadas, en orden de tiempo.
func (s *Store) PendingLogs(ctx context.Context, limit int) ([]Log, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, employee_id, credential_id, door_id, timestamp, direction, status, denial_reason, method, source, raw
		FROM log_queue
		WHERE sent_at IS NULL
		ORDER BY timestamp, created_at
		LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer func() { _ = rows.Close() }()
	var logs []Log
	for rows.Next() {
		var item Log
		var employee, credential, door sql.NullString
		var stamp string
		if err := rows.Scan(&item.ID, &employee, &credential, &door, &stamp, &item.Direction, &item.Status, &item.DenialReason, &item.Method, &item.Source, &item.Raw); err != nil {
			return nil, err
		}
		parsed, err := protocol.ParseTime(stamp)
		if err != nil {
			return nil, err
		}
		item.Timestamp = parsed
		item.EmployeeID = employee.String
		item.CredentialID = credential.String
		item.DoorID = door.String
		logs = append(logs, item)
	}
	return logs, rows.Err()
}

// MarkLogsSent marca como enviadas las marcaciones que la nube ya respondió.
func (s *Store) MarkLogsSent(ctx context.Context, ids []string, at time.Time) error {
	stamp := protocol.FormatTime(at)
	for _, id := range ids {
		if id == "" {
			continue
		}
		if _, err := s.db.ExecContext(ctx, `UPDATE log_queue SET sent_at = ? WHERE id = ? AND sent_at IS NULL`, stamp, id); err != nil {
			return err
		}
	}
	return nil
}

// PurgeSent borra marcaciones enviadas más viejas que before.
func (s *Store) PurgeSent(ctx context.Context, before time.Time) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM log_queue WHERE sent_at IS NOT NULL AND sent_at < ?`, protocol.FormatTime(before))
	return err
}

// LookupReader busca un lector por el device_id del gateway.
func (s *Store) LookupReader(ctx context.Context, deviceID string) (ReaderView, bool, error) {
	var view ReaderView
	var readerActive, doorActive, face, profileActive int
	var normalization string
	err := s.db.QueryRowContext(ctx, `
		SELECT r.id, r.reader_device_id, r.is_active,
		       d.id, d.name, d.relay_device_id, d.direction, d.apb_mode, d.face_enabled, d.is_active,
		       p.id, p.credential_type, p.normalization, p.min_length, p.max_length, p.is_active
		FROM readers r
		JOIN doors d ON d.id = r.door_id
		JOIN reader_profiles p ON p.id = r.reader_profile_id
		WHERE r.reader_device_id = ?
		ORDER BY r.is_active DESC, r.version DESC
		LIMIT 1
	`, deviceID).Scan(
		&view.ReaderID, &view.DeviceID, &readerActive,
		&view.Door.ID, &view.Door.Name, &view.Door.RelayDeviceID, &view.Door.Direction, &view.Door.ApbMode, &face, &doorActive,
		&view.ProfileID, &view.CredentialType, &normalization, &view.MinLength, &view.MaxLength, &profileActive,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return ReaderView{}, false, nil
	}
	if err != nil {
		return ReaderView{}, false, err
	}
	if err := json.Unmarshal([]byte(normalization), &view.Steps); err != nil {
		return ReaderView{}, false, err
	}
	view.ReaderActive = readerActive == 1
	view.Door.FaceEnabled = face == 1
	view.Door.IsActive = doorActive == 1
	view.ProfileActive = profileActive == 1
	return view, true, nil
}

// LookupDoor busca una puerta por id.
func (s *Store) LookupDoor(ctx context.Context, id string) (Door, bool, error) {
	var door Door
	var face, active int
	err := s.db.QueryRowContext(ctx, `
		SELECT id, name, relay_device_id, direction, apb_mode, face_enabled, is_active
		FROM doors WHERE id = ?
	`, id).Scan(&door.ID, &door.Name, &door.RelayDeviceID, &door.Direction, &door.ApbMode, &face, &active)
	if errors.Is(err, sql.ErrNoRows) {
		return Door{}, false, nil
	}
	if err != nil {
		return Door{}, false, err
	}
	door.FaceEnabled = face == 1
	door.IsActive = active == 1
	return door, true, nil
}

// LookupCredential devuelve la credencial activa si existe; si no, una inactiva del mismo par.
func (s *Store) LookupCredential(ctx context.Context, credentialType, payload string) (Credential, bool, error) {
	var item Credential
	var active int
	var from, until sql.NullString
	err := s.db.QueryRowContext(ctx, `
		SELECT id, employee_id, type, payload, is_active, valid_from, valid_until
		FROM credentials
		WHERE type = ? AND payload = ?
		ORDER BY is_active DESC, version DESC
		LIMIT 1
	`, credentialType, payload).Scan(&item.ID, &item.EmployeeID, &item.Type, &item.Payload, &active, &from, &until)
	if errors.Is(err, sql.ErrNoRows) {
		return Credential{}, false, nil
	}
	if err != nil {
		return Credential{}, false, err
	}
	item.IsActive = active == 1
	item.ValidFrom, err = parseOptional(from)
	if err != nil {
		return Credential{}, false, err
	}
	item.ValidUntil, err = parseOptional(until)
	if err != nil {
		return Credential{}, false, err
	}
	return item, true, nil
}

func parseOptional(value sql.NullString) (*time.Time, error) {
	if !value.Valid || strings.TrimSpace(value.String) == "" {
		return nil, nil
	}
	parsed, err := protocol.ParseTime(value.String)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}

// EmployeeActive indica si el empleado existe y si está activo.
func (s *Store) EmployeeActive(ctx context.Context, id string) (exists bool, active bool, err error) {
	var flag int
	err = s.db.QueryRowContext(ctx, `SELECT is_active FROM employees WHERE id = ?`, id).Scan(&flag)
	if errors.Is(err, sql.ErrNoRows) {
		return false, false, nil
	}
	if err != nil {
		return false, false, err
	}
	return true, flag == 1, nil
}

// State devuelve el anti-passback local. El delta no pisa un estado ya decidido aquí.
func (s *Store) State(ctx context.Context, employeeID string) (inside bool, err error) {
	var flag int
	err = s.db.QueryRowContext(ctx, `SELECT is_inside FROM employee_state WHERE employee_id = ?`, employeeID).Scan(&flag)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return flag == 1, nil
}

// SaveState actualiza la presencia local.
func (s *Store) SaveState(ctx context.Context, employeeID string, inside bool, at time.Time) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO employee_state (employee_id, is_inside, last_event_at)
		VALUES (?, ?, ?)
		ON CONFLICT(employee_id) DO UPDATE SET
			is_inside = excluded.is_inside,
			last_event_at = excluded.last_event_at
	`, employeeID, boolInt(inside), protocol.FormatTime(at))
	return err
}

// ArmEnrollment abre una ventana en la que el lector no valida.
func (s *Store) ArmEnrollment(ctx context.Context, readerID, commandID string, until time.Time) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO enrollment_windows (reader_id, command_id, until_at)
		VALUES (?, ?, ?)
		ON CONFLICT(reader_id) DO UPDATE SET
			command_id = excluded.command_id,
			until_at = excluded.until_at
	`, readerID, commandID, protocol.FormatTime(until))
	return err
}

// Enrollment devuelve la ventana vigente de un lector.
func (s *Store) Enrollment(ctx context.Context, readerID string, now time.Time) (commandID string, ok bool, err error) {
	var until string
	err = s.db.QueryRowContext(ctx, `
		SELECT command_id, until_at FROM enrollment_windows WHERE reader_id = ?
	`, readerID).Scan(&commandID, &until)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	deadline, err := protocol.ParseTime(until)
	if err != nil {
		return "", false, err
	}
	if !now.Before(deadline) {
		return "", false, nil
	}
	return commandID, true, nil
}

// EnqueueEnrollment guarda una lectura para reintento.
func (s *Store) EnqueueEnrollment(ctx context.Context, sample EnrollmentSample) (int64, error) {
	result, err := s.db.ExecContext(ctx, `
		INSERT INTO enrollment_outbox
			(reader_id, command_id, raw, payload, credential_type, error, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`, sample.ReaderID, sample.CommandID, sample.Raw, sample.Payload, sample.CredentialType, sample.Error, protocol.FormatTime(time.Now()))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

// PendingEnrollment devuelve lecturas que todavía no confirmó la nube.
func (s *Store) PendingEnrollment(ctx context.Context, limit int) ([]EnrollmentSample, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, reader_id, command_id, raw, payload, credential_type, error, created_at
		FROM enrollment_outbox
		ORDER BY id
		LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer func() { _ = rows.Close() }()
	var samples []EnrollmentSample
	for rows.Next() {
		var item EnrollmentSample
		var created string
		if err := rows.Scan(&item.ID, &item.ReaderID, &item.CommandID, &item.Raw, &item.Payload, &item.CredentialType, &item.Error, &created); err != nil {
			return nil, err
		}
		parsed, err := protocol.ParseTime(created)
		if err != nil {
			return nil, err
		}
		item.CreatedAt = parsed
		samples = append(samples, item)
	}
	return samples, rows.Err()
}

// DeleteEnrollment quita lecturas ya entregadas.
func (s *Store) DeleteEnrollment(ctx context.Context, ids []int64) error {
	for _, id := range ids {
		if _, err := s.db.ExecContext(ctx, `DELETE FROM enrollment_outbox WHERE id = ?`, id); err != nil {
			return err
		}
	}
	return nil
}

// ActiveDevices lista los device_id que el agente debe escuchar.
func (s *Store) ActiveDevices(ctx context.Context) ([]string, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT DISTINCT r.reader_device_id
		FROM readers r
		JOIN doors d ON d.id = r.door_id
		WHERE r.is_active = 1 AND d.is_active = 1 AND r.reader_device_id != ''
		ORDER BY r.reader_device_id
	`)
	if err != nil {
		return nil, err
	}
	defer func() { _ = rows.Close() }()
	var devices []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		devices = append(devices, id)
	}
	if devices == nil {
		devices = []string{}
	}
	return devices, rows.Err()
}

// CountDoors ayuda a las pruebas de resync.
func (s *Store) CountDoors(ctx context.Context) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM doors`).Scan(&count)
	return count, err
}
