export const TIME_ZONES = [
  "UTC",
  "America/Bogota",
  "America/Lima",
  "America/Mexico_City",
  "America/Guayaquil",
  "America/Caracas",
  "America/Santiago",
  "America/Argentina/Buenos_Aires",
  "America/Sao_Paulo",
  "America/New_York",
  "Europe/Madrid",
];

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function zoneOptions(current?: string | null): string[] {
  if (current && !TIME_ZONES.includes(current)) {
    return [current, ...TIME_ZONES];
  }
  return TIME_ZONES;
}

function wallClockToUtc(value: string, timeZone: string): string | null {
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  let utc = Date.parse(`${withSeconds}Z`);
  if (Number.isNaN(utc)) {
    return null;
  }
  const wanted = utc;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const shown = toDateTimeLocal(new Date(utc).toISOString(), timeZone);
    if (!shown) {
      return null;
    }
    const shownMs = Date.parse(`${shown}:00Z`);
    const delta = wanted - shownMs;
    if (delta === 0) {
      break;
    }
    utc += delta;
  }
  return new Date(utc).toISOString();
}

export function toDateTimeLocal(iso: string | null, timeZone: string): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  const hour = read("hour") === "24" ? "00" : read("hour");
  return `${read("year")}-${read("month")}-${read("day")}T${hour}:${read("minute")}`;
}

export function fromDateTimeLocal(value: string, timeZone: string): string | null {
  if (!value) {
    return null;
  }
  return wallClockToUtc(value, timeZone);
}

export function startOfDayIso(date: string, timeZone: string): string | undefined {
  if (!date) {
    return undefined;
  }
  return fromDateTimeLocal(`${date}T00:00`, timeZone) ?? undefined;
}

export function endOfDayIso(date: string, timeZone: string): string | undefined {
  if (!date) {
    return undefined;
  }
  return fromDateTimeLocal(`${date}T23:59`, timeZone) ?? undefined;
}

export function formatStamp(iso: string | null | undefined, timeZone: string): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("es-CO", {
    timeZone,
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
}

export function formatAgo(iso: string | null | undefined): string {
  if (!iso) {
    return "sin latido";
  }
  const delta = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(delta)) {
    return "sin latido";
  }
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) {
    return "hace un momento";
  }
  if (minutes < 60) {
    return `hace ${minutes} min`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `hace ${hours} h`;
  }
  return `hace ${Math.round(hours / 24)} d`;
}
