import { create } from "zustand";
import { persist } from "zustand/middleware";

import { browserTimeZone } from "@/lib/time";

export type LogFilters = {
  timestamp_after: string;
  timestamp_before: string;
  node: string;
  door: string;
  employee: string;
  status: string;
  denial_reason: string;
  method: string;
  source: string;
};

export const emptyLogFilters: LogFilters = {
  timestamp_after: "",
  timestamp_before: "",
  node: "",
  door: "",
  employee: "",
  status: "",
  denial_reason: "",
  method: "",
  source: "",
};

type PreferencesState = {
  theme: "light" | "dark";
  timeZone: string;
  employeeSearch: string;
  logFilters: LogFilters;
  setTheme: (theme: "light" | "dark") => void;
  setTimeZone: (timeZone: string) => void;
  setEmployeeSearch: (employeeSearch: string) => void;
  setLogFilters: (logFilters: LogFilters) => void;
};

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: "light",
      timeZone: browserTimeZone(),
      employeeSearch: "",
      logFilters: emptyLogFilters,
      setTheme: (theme) => set({ theme }),
      setTimeZone: (timeZone) => set({ timeZone }),
      setEmployeeSearch: (employeeSearch) => set({ employeeSearch }),
      setLogFilters: (logFilters) => set({ logFilters }),
    }),
    {
      name: "attendance-preferences",
      skipHydration: true,
      onRehydrateStorage: () => () => {
        usePreferences.setState({ theme: usePreferences.getState().theme });
      },
    },
  ),
);

export function resetPreferences(): void {
  usePreferences.setState({
    theme: "light",
    timeZone: "America/Bogota",
    employeeSearch: "",
    logFilters: emptyLogFilters,
  });
}
