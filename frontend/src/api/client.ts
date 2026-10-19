import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { notifySessionExpired, readTokens, writeTokens } from "@/auth/memory";

import type { Me, Page, QueryParams, TokenPair } from "./types";

export const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const http = axios.create({ baseURL: apiBaseUrl });

http.interceptors.request.use((config) => {
  const { access } = readTokens();
  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

type RetryConfig = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  const { refresh } = readTokens();
  if (!refresh) {
    return null;
  }
  try {
    const response = await axios.post<{ access: string }>(`${apiBaseUrl}/auth/token/refresh/`, {
      refresh,
    });
    writeTokens({ access: response.data.access, refresh });
    return response.data.access;
  } catch {
    return null;
  }
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;
    const url = original?.url ?? "";
    if (
      !original ||
      error.response?.status !== 401 ||
      original._retry ||
      url.includes("/auth/token")
    ) {
      return Promise.reject(error);
    }
    original._retry = true;
    refreshPromise ??= refreshAccess().finally(() => {
      refreshPromise = null;
    });
    const access = await refreshPromise;
    if (!access) {
      notifySessionExpired();
      return Promise.reject(error);
    }
    original.headers.Authorization = `Bearer ${access}`;
    return http(original);
  },
);

function cleanParams(params?: QueryParams) {
  if (!params) {
    return undefined;
  }
  return Object.fromEntries(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    ),
  );
}

export const api = {
  async login(username: string, password: string): Promise<TokenPair> {
    const response = await http.post<TokenPair>("/auth/token/", { username, password });
    return response.data;
  },

  async me(): Promise<Me> {
    const response = await http.get<Me>("/auth/me/");
    return response.data;
  },

  async switchOrganization(organizationId: string): Promise<TokenPair> {
    const response = await http.post<TokenPair>("/auth/switch-organization/", {
      organization_id: organizationId,
    });
    return response.data;
  },

  async list<T>(path: string, params?: QueryParams): Promise<Page<T>> {
    const response = await http.get<Page<T>>(path, { params: cleanParams(params) });
    return response.data;
  },

  async get<T>(path: string, params?: QueryParams): Promise<T> {
    const response = await http.get<T>(path, { params: cleanParams(params) });
    return response.data;
  },

  async create<T>(path: string, body?: unknown): Promise<T> {
    const response = await http.post<T>(path, body ?? {});
    return response.data;
  },

  async update<T>(path: string, body: unknown): Promise<T> {
    const response = await http.patch<T>(path, body);
    return response.data;
  },

  async remove(path: string): Promise<void> {
    await http.delete(path);
  },

  async download(path: string, filename: string): Promise<void> {
    const response = await http.get(path, { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
