import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Me, Role, TokenPair } from "@/api/types";
import {
  setSessionExpiredHandler,
  setTokenListener,
  writeTokens,
  type Tokens,
} from "@/auth/memory";

type SessionState = {
  access: string | null;
  refresh: string | null;
  organizationId: string | null;
  role: Role | null;
  isSuperadmin: boolean;
  user: Me | null;
  hydrated: boolean;
  applyTokens: (tokens: TokenPair) => void;
  setUser: (user: Me) => void;
  clear: () => void;
};

const empty = {
  access: null,
  refresh: null,
  organizationId: null,
  role: null,
  isSuperadmin: false,
  user: null,
};

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      ...empty,
      hydrated: false,
      applyTokens: (tokens) => {
        writeTokens({ access: tokens.access, refresh: tokens.refresh });
        set({
          access: tokens.access,
          refresh: tokens.refresh,
          organizationId: tokens.organization_id,
          role: tokens.role,
          isSuperadmin: tokens.is_superadmin,
        });
      },
      setUser: (user) => {
        set({
          user,
          organizationId: user.organization_id,
          role: user.role,
          isSuperadmin: user.is_superadmin,
        });
      },
      clear: () => {
        writeTokens({ access: null, refresh: null });
        set(empty);
      },
    }),
    {
      name: "attendance-session",
      skipHydration: true,
      partialize: (state) => ({
        access: state.access,
        refresh: state.refresh,
        organizationId: state.organizationId,
        role: state.role,
        isSuperadmin: state.isSuperadmin,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.access) {
          writeTokens({ access: state.access, refresh: state.refresh });
        }
        useSession.setState({ hydrated: true });
      },
    },
  ),
);

setTokenListener((next: Tokens) => {
  const state = useSession.getState();
  if (state.access === next.access && state.refresh === next.refresh) {
    return;
  }
  useSession.setState({ access: next.access, refresh: next.refresh });
});

setSessionExpiredHandler(() => {
  useSession.getState().clear();
});

export function resetSession(): void {
  useSession.setState({ ...empty, hydrated: true });
  writeTokens({ access: null, refresh: null });
}
