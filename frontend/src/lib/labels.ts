import type { Role } from "@/api/types";

export const ROLE_LABEL: Record<Role, string> = {
  SUPERADMIN: "Plataforma",
  ADMIN: "Administrador",
  OPERATOR: "Operador",
  VIEWER: "Consulta",
};

export const CREDENTIAL_TYPE_LABEL: Record<string, string> = {
  RFID: "Tarjeta RFID",
  FINGERPRINT: "Huella",
  PIN: "PIN",
  FACIAL: "Rostro",
};

export const CREDENTIAL_SOURCE_LABEL: Record<string, string> = {
  MANUAL: "Manual",
  ASSISTED_ENROLLMENT: "Enrolamiento asistido",
  FACEAUTH: "Face-Auth",
};

export const DIRECTION_LABEL: Record<string, string> = {
  IN: "Ingreso",
  OUT: "Salida",
};

export const APB_LABEL: Record<string, string> = {
  OFF: "Apagado",
  SOFT: "Blando",
  HARD: "Duro",
};

export const STATUS_LABEL: Record<string, string> = {
  GRANTED: "Concedido",
  DENIED: "Denegado",
};

export const METHOD_LABEL: Record<string, string> = {
  RFID: "RFID",
  FINGERPRINT: "Huella",
  FACIAL: "Rostro",
  PIN: "PIN",
  REMOTE: "Apertura remota",
};

export const SOURCE_LABEL: Record<string, string> = {
  gateway: "Gateway",
  cloud: "Nube",
  remote: "Remoto",
};

export const DENIAL_LABEL: Record<string, string> = {
  UNKNOWN_CREDENTIAL: "Credencial desconocida",
  INACTIVE: "Inactiva",
  EXPIRED: "Vencida",
  APB_VIOLATION: "Anti-passback",
  UNKNOWN_DEVICE: "Dispositivo desconocido",
  MALFORMED_READ: "Lectura mal formada",
  FACE_NOT_ALLOWED: "Rostro no habilitado",
  NODE_OFFLINE: "Nodo sin conexión",
};

export const ANOMALY_LABEL: Record<string, string> = {
  APB_REPORTED: "Anti-passback reportado",
  APB_CONFLICT: "Conflicto entre nodos",
  OCCUPANCY_DRIFT: "Aforo corregido",
  STATE_RESET: "Reinicio de estado",
};

export const ATTENDANCE_LABEL: Record<string, string> = {
  PRESENT: "Presente",
  LATE: "Tarde",
  EARLY_LEAVE: "Salida anticipada",
  INCOMPLETE: "Marca huérfana",
  ABSENT: "Ausente",
  HOLIDAY: "Festivo",
};

export const WEBHOOK_EVENT_LABEL: Record<string, string> = {
  "access.granted": "Acceso concedido",
  "access.denied": "Acceso denegado",
  "device.status_changed": "Estado del nodo",
  "employee.updated": "Empleado actualizado",
  "occupancy.threshold": "Umbral de aforo",
  "face.enrolled": "Rostro enrolado",
};

export const WEBHOOK_STATUS_LABEL: Record<string, string> = {
  PENDING: "Pendiente",
  SUCCESS: "Entregado",
  FAILED: "Fallido",
  EXHAUSTED: "Agotado",
};

export const WEEKDAY_LABEL = ["", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export const COMMAND_STATUS_LABEL: Record<string, string> = {
  PENDING: "Pendiente",
  SENT: "Enviado",
  ACKED: "Confirmado",
  FAILED: "Fallido",
  EXPIRED: "Expirado",
};

export function labelOf(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  return map[value] ?? value;
}

export function personName(person: { first_name: string; last_name: string }): string {
  return `${person.first_name} ${person.last_name}`.trim();
}
