import { useQuery, type QueryKey } from "@tanstack/react-query";

import { useSession } from "@/auth/session";

type Options = {
  enabled?: boolean;
  refetchInterval?: number | false;
  scoped?: boolean;
};

export function useOrgQuery<T>(key: QueryKey, queryFn: () => Promise<T>, options?: Options) {
  const organizationId = useSession((state) => state.organizationId);
  const scoped = options?.scoped ?? true;
  const enabled = (scoped ? Boolean(organizationId) : true) && (options?.enabled ?? true);
  return useQuery({
    queryKey: [scoped ? organizationId : "platform", ...key],
    queryFn,
    enabled,
    refetchInterval: options?.refetchInterval,
  });
}
