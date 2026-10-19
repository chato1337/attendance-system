import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { FaceCapture } from "./FaceCapture";
import { loginFace } from "./faceAuthApi";

class FakeRecorder {
  static isTypeSupported() {
    return true;
  }

  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = "inactive";

  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: new Blob(["clip"], { type: "video/webm" }) });
  }

  stop() {
    this.state = "inactive";
    this.onstop?.();
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FaceCapture", () => {
  test("entrega el clip y no lo vuelve a pedir", async () => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    const stop = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const onClip = vi.fn();
    render(<FaceCapture durationMs={0} onClip={onClip} />);
    const button = await screen.findByRole("button", { name: "Ingresar con rostro" });
    fireEvent.click(button);
    await waitFor(() => expect(onClip).toHaveBeenCalledOnce());
    const clip = onClip.mock.calls[0][0] as Blob;
    expect(clip.size).toBeGreaterThan(0);
    expect(clip.type).toContain("webm");
  });

  test("avisa si el navegador no puede grabar", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    render(<FaceCapture onClip={vi.fn()} />);
    expect(screen.getByText(/no puede grabar video/i)).toBeInTheDocument();
  });
});

describe("faceAuthApi", () => {
  test("el login va directo a Face-Auth y no envía la api_key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: "user-1", tokens: { redirect_token: "once" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await loginFace("http://face.test/api/v1/", "app_1", new Blob(["v"]));
    expect(result.redirectToken).toBe("once");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://face.test/api/v1/auth/login/");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-App-Id"]).toBe("app_1");
    expect(headers["X-Api-Key"]).toBeUndefined();
    expect(JSON.stringify(headers).toLowerCase()).not.toContain("api_key");
    expect(init.body).toBeInstanceOf(FormData);
  });
});
