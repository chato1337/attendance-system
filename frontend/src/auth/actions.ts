import type { QueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";

import { useSession } from "./session";

export async function changeOrganization(organizationId: string, queryClient: QueryClient) {
  const tokens = await api.switchOrganization(organizationId);
  useSession.getState().applyTokens(tokens);
  queryClient.clear();
  const user = await api.me();
  useSession.getState().setUser(user);
}
