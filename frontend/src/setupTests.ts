import "@testing-library/jest-dom/vitest";
import { beforeEach, vi, type Mock } from "vitest";

import { api } from "@/api/client";
import { resetPreferences } from "@/auth/preferences";
import { resetSession } from "@/auth/session";

vi.mock("@/api/client", () => ({
  apiBaseUrl: "http://localhost:8000/api/v1",
  http: {},
  api: {
    login: vi.fn(),
    me: vi.fn(),
    switchOrganization: vi.fn(),
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}));

const mocked = api as unknown as {
  list: Mock;
  get: Mock;
  create: Mock;
  update: Mock;
  remove: Mock;
};

beforeEach(() => {
  localStorage.clear();
  resetSession();
  resetPreferences();
  vi.clearAllMocks();
  mocked.list.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  mocked.get.mockResolvedValue([]);
  mocked.create.mockResolvedValue({});
  mocked.update.mockResolvedValue({});
  mocked.remove.mockResolvedValue(undefined);
});
