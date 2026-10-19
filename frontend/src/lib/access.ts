import type { Role } from "@/api/types";

export function canOperate(role: Role | null): boolean {
  return role === "ADMIN" || role === "OPERATOR" || role === "SUPERADMIN";
}

export function canAdminister(role: Role | null): boolean {
  return role === "ADMIN" || role === "SUPERADMIN";
}

export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
