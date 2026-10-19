import axios from "axios";

function flatten(value: unknown): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("<")) {
      return "La API respondió con un error interno.";
    }
    return trimmed.length > 280 ? `${trimmed.slice(0, 280)}…` : trimmed;
  }
  if (Array.isArray(value)) {
    return value.map(flatten).filter(Boolean).join(" ");
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.detail === "string" || Array.isArray(record.detail)) {
      return flatten(record.detail);
    }
    return Object.entries(record)
      .map(([key, item]) => {
        const text = flatten(item);
        return text ? `${key}: ${text}` : "";
      })
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const text = flatten(error.response?.data);
    if (text) {
      return text;
    }
    if (!error.response) {
      return "No hay conexión con la API.";
    }
  }
  return "No se pudo completar la operación.";
}
