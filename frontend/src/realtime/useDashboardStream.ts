import { useEffect, useRef, useState } from "react";

import { readTokens } from "@/auth/memory";
import { useSession } from "@/auth/session";

import { dashboardSocketUrl } from "./events";
import type { LiveMessage } from "@/api/types";

export type StreamStatus = "idle" | "offline" | "live" | "reconnecting";

export function useDashboardStream(onEvent: (message: LiveMessage) => void) {
  const access = useSession((state) => state.access);
  const organizationId = useSession((state) => state.organizationId);
  const [status, setStatus] = useState<StreamStatus>(
    import.meta.env.MODE === "test" ? "idle" : "offline",
  );
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (import.meta.env.MODE === "test" || !access) {
      return;
    }
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let timer = 0;

    const connect = () => {
      setStatus(attempt === 0 ? "offline" : "reconnecting");
      socket = new WebSocket(dashboardSocketUrl());
      socket.onopen = () => {
        attempt = 0;
        socket?.send(JSON.stringify({ op: "auth", token: readTokens().access }));
      };
      socket.onmessage = (event) => {
        const body = JSON.parse(String(event.data)) as LiveMessage & { op?: string };
        if (body.op === "auth_ok") {
          setStatus("live");
          return;
        }
        if (body.event) {
          handler.current(body);
        }
      };
      socket.onclose = () => {
        if (stopped) {
          return;
        }
        setStatus("reconnecting");
        attempt += 1;
        const delay = Math.min(10_000, 500 * 2 ** attempt);
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [access, organizationId]);

  return status;
}
