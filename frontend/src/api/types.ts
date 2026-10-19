export type Role = "ADMIN" | "OPERATOR" | "VIEWER" | "SUPERADMIN";

export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type TokenPair = {
  access: string;
  refresh: string;
  organization_id: string | null;
  role: Role | null;
  is_superadmin: boolean;
};

export type MembershipSummary = {
  organization_id: string;
  name: string;
  slug: string;
  role: Exclude<Role, "SUPERADMIN">;
};

export type Me = {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_superadmin: boolean;
  organization_id: string | null;
  role: Role | null;
  memberships: MembershipSummary[];
};

export type Department = {
  id: string;
  organization: string;
  name: string;
  is_active: boolean;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Employee = {
  id: string;
  organization: string;
  department: string | null;
  document_id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  is_active: boolean;
  is_inside: boolean;
  last_presence_at: string | null;
  presence_node: string | null;
  presence_zone: string | null;
  presence_reset_at: string | null;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type CredentialType = "FACIAL" | "FINGERPRINT" | "RFID" | "PIN";
export type CredentialSource = "MANUAL" | "ASSISTED_ENROLLMENT" | "FACEAUTH";

export type Credential = {
  id: string;
  organization: string;
  employee: string;
  type: CredentialType;
  payload: string;
  source: CredentialSource;
  reader_profile: string | null;
  is_active: boolean;
  valid_from: string | null;
  valid_until: string | null;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Zone = Department;

export type NormOp =
  | "trim"
  | "upper"
  | "strip_leading_zeros"
  | "regex_extract"
  | "hex_to_dec"
  | "dec_to_hex"
  | "pad_left";

export type NormStep = {
  op: NormOp;
  pattern?: string;
  length?: number;
  char?: string;
};

export type ReaderProfile = {
  id: string;
  organization: string;
  name: string;
  credential_type: CredentialType;
  normalization: NormStep[];
  min_length: number;
  max_length: number;
  is_active: boolean;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type AccessNode = {
  id: string;
  organization: string;
  name: string;
  site: string;
  timezone: string;
  is_active: boolean;
  is_online: boolean;
  last_heartbeat_at: string | null;
  last_sync_at: string | null;
  last_sync_version: number;
  gateway_version_reported: string;
  agent_version: string;
  gateway_connected: boolean;
  listening_devices: string[];
  queue_size: number;
  commands_connected: boolean;
  api_key: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Direction = "IN" | "OUT";
export type ApbMode = "OFF" | "SOFT" | "HARD";

export type Door = {
  id: string;
  organization: string;
  node: string;
  zone: string | null;
  name: string;
  relay_device_id: string;
  direction: Direction;
  apb_mode: ApbMode;
  required_factors: string[];
  face_enabled: boolean;
  is_active: boolean;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Reader = {
  id: string;
  organization: string;
  door: string;
  reader_profile: string;
  name: string;
  reader_device_id: string;
  is_active: boolean;
  deleted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type AccessStatus = "GRANTED" | "DENIED";
export type AccessMethod = "RFID" | "FINGERPRINT" | "FACIAL" | "PIN" | "REMOTE";
export type AccessSource = "gateway" | "cloud" | "remote";

export type AccessLog = {
  id: string;
  organization: string;
  node: string;
  door: string | null;
  employee: string | null;
  credential: string | null;
  timestamp: string;
  direction: Direction;
  status: AccessStatus;
  denial_reason: string;
  method: string;
  source: string;
  created_at: string;
};

export type OccupancySite = {
  node_id: string | null;
  name: string;
  site: string;
  inside: number;
};

export type OccupancyZone = {
  zone_id: string | null;
  name: string;
  inside: number;
};

export type Occupancy = {
  total_inside: number;
  sites: OccupancySite[];
  zones: OccupancyZone[];
};

export type AnomalyKind = "APB_REPORTED" | "APB_CONFLICT" | "OCCUPANCY_DRIFT" | "STATE_RESET";

export type AccessAnomaly = {
  id: string;
  organization: string;
  node: string | null;
  access_log: string | null;
  employee: string | null;
  kind: AnomalyKind;
  detail: Record<string, unknown>;
  created_at: string;
};

export type LiveMessage = {
  event: string;
  organization_id: string;
  occurred_at: string;
  data: Record<string, unknown>;
};

export type Kiosk = {
  id: string;
  organization: string;
  door: string;
  name: string;
  is_active: boolean;
  last_seen_at: string | null;
  camera_permission: "unknown" | "granted" | "denied" | "prompt";
  kiosk_token: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type KioskMe = {
  kiosk_id: string;
  name: string;
  door_id: string;
  door_name: string;
  direction: string;
  organization_name: string;
  organization_slug: string;
  face_enabled: boolean;
  faceauth_enabled: boolean;
  app_id: string;
  api_url: string;
  web_url: string;
  allow_kiosk_self_enrollment: boolean;
  camera_permission: string;
};

export type FaceIdentifyResult = {
  id: string;
  status: string;
  code: string;
  message: string;
  door_id: string;
  kiosk_id: string;
  log_id: string | null;
};

export type FaceIntegration = {
  id: string;
  app_id: string;
  api_key_set: boolean;
  api_url: string;
  server_api_url: string;
  web_url: string;
  enabled: boolean;
  allow_panel_login: boolean;
  allow_kiosk_self_enrollment: boolean;
  cors_origins: string[];
  hosted_redirect_uris: string[];
};

export type FaceEnrollmentSession = {
  id: string;
  employee: string;
  employee_name: string;
  started_by: string;
  status: string;
  failure_code: string;
  created_at: string;
  expires_at: string;
};

export type FaceMetrics = {
  window_hours: number;
  identifications: Record<string, number>;
  codes: Record<string, number>;
  verify_ms_p95: number | null;
  camera_permission: Record<string, number>;
  pending_deletions: number;
  enabled: boolean;
};

export type FaceEnrollmentStart = {
  id: string;
  status: string;
  failure_code: string;
  app_id: string;
  api_url: string;
  web_url: string;
  email: string;
  first_name: string;
  last_name: string;
};

export type FaceReadiness = {
  id: string;
  document_id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  issues: string[];
};

export type FaceLoginOptions = {
  allow_panel_login: boolean;
  org_slug?: string;
  app_id?: string;
  api_url?: string;
  web_url?: string;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Membership = {
  id: string;
  user_id: string;
  user_username: string;
  user_email: string;
  role: Exclude<Role, "SUPERADMIN">;
  created_at: string;
};

export type CommandStatus = "PENDING" | "SENT" | "ACKED" | "FAILED" | "EXPIRED";

export type EdgeCommand = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  status: CommandStatus;
  expires_at: string;
  result: Record<string, unknown> | null;
  created_at: string;
  sent_at: string | null;
  acked_at: string | null;
};

export type EnrollmentRead = {
  id: string;
  node: string;
  reader: string | null;
  command: string | null;
  raw: string;
  payload: string;
  credential_type: string;
  error: string;
  created_at: string;
};

export type PreviewResult = {
  ok: boolean;
  payload?: string;
  error?: string;
};

export type Shift = {
  id: string;
  organization: string;
  name: string;
  start_time: string;
  end_time: string;
  late_tolerance_minutes: number;
  early_leave_tolerance_minutes: number;
  is_active: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkSchedule = {
  id: string;
  organization: string;
  shift: string;
  shift_name: string;
  employee: string | null;
  employee_name: string;
  department: string | null;
  department_name: string;
  weekdays: number[];
  is_active: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Holiday = {
  id: string;
  organization: string;
  date: string;
  name: string;
  created_at: string;
};

export type AttendanceStatus =
  | "PRESENT"
  | "LATE"
  | "EARLY_LEAVE"
  | "INCOMPLETE"
  | "ABSENT"
  | "HOLIDAY";

export type DailyAttendance = {
  id: string;
  employee: string;
  document_id: string;
  employee_name: string;
  department: string | null;
  department_name: string;
  site: string;
  work_date: string;
  status: AttendanceStatus;
  is_holiday: boolean;
  scheduled: boolean;
  expected_start: string | null;
  expected_end: string | null;
  first_in: string | null;
  last_out: string | null;
  worked_minutes: number;
  late_minutes: number;
  early_leave_minutes: number;
  orphan_in: boolean;
  granted_count: number;
};

export type AttendanceDepartmentBar = {
  department_id: string | null;
  name: string;
  worked_minutes: number;
  late_days: number;
  absent_days: number;
  employees: number;
};

export type AttendanceDayBar = {
  date: string;
  present: number;
  absent: number;
  late: number;
  worked_minutes: number;
};

export type AttendanceSummary = {
  date_from: string;
  date_to: string;
  employees: number;
  expected_days: number;
  present_days: number;
  late_days: number;
  early_leave_days: number;
  absent_days: number;
  incomplete_days: number;
  holiday_days: number;
  worked_minutes: number;
  punctuality_rate: number | null;
  absenteeism_rate: number | null;
  by_department: AttendanceDepartmentBar[];
  by_day: AttendanceDayBar[];
};

export type ExportFormat = "csv" | "xlsx" | "pdf" | "json";
export type ExportStatus = "PENDING" | "RUNNING" | "READY" | "FAILED";

export type ExportJob = {
  id: string;
  format: ExportFormat;
  status: ExportStatus;
  filters: Record<string, string | null>;
  row_count: number;
  error: string;
  download_url: string | null;
  expires_at: string;
  created_at: string;
};

export type WebhookSubscription = {
  id: string;
  name: string;
  url: string;
  secret_value?: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type WebhookDelivery = {
  id: string;
  subscription: string;
  event: string;
  payload: Record<string, unknown>;
  attempt: number;
  status: "PENDING" | "SUCCESS" | "FAILED" | "EXHAUSTED";
  response_status: number | null;
  response_body: string;
  next_retry_at: string | null;
  created_at: string;
  completed_at: string | null;
};

export type APIToken = {
  id: string;
  name: string;
  token?: string;
  token_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
};

export type QueryParams = Record<string, string | number | boolean | undefined | null>;
