import { expect, test } from "@playwright/test";

test.use({
  permissions: ["camera"],
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  },
});

test("el kiosco marca con rostro sin enviar el video a nuestra API", async ({ page }) => {
  await page.addInitScript(() => {
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
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeRecorder });
    const mediaDevices = navigator.mediaDevices ?? ({} as MediaDevices);
    mediaDevices.getUserMedia = async () =>
      ({ getTracks: () => [{ stop() {} }] }) as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: mediaDevices });
  });

  const ourBodies: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST") {
      ourBodies.push(request.postData() ?? "");
    }
    if (path.endsWith("/kiosk/me/")) {
      await route.fulfill({
        json: {
          kiosk_id: "k1",
          name: "Recepción",
          door_id: "d1",
          door_name: "Principal",
          direction: "IN",
          organization_name: "Acme",
          organization_slug: "acme",
          face_enabled: true,
          faceauth_enabled: true,
          app_id: "app_acme",
          api_url: "http://faceauth.test/api/v1",
          web_url: "http://faceauth.test",
          allow_kiosk_self_enrollment: false,
          camera_permission: "granted",
        },
      });
      return;
    }
    if (path.endsWith("/kiosk/heartbeat/")) {
      await route.fulfill({ json: { camera_permission: "granted" } });
      return;
    }
    if (path.endsWith("/kiosk/face-identify/")) {
      await route.fulfill({
        json: {
          id: "req-1",
          status: "GRANTED",
          code: "",
          message: "Acceso concedido.",
          door_id: "d1",
          kiosk_id: "k1",
          log_id: null,
        },
      });
      return;
    }
    await route.fulfill({ status: 404, json: {} });
  });
  await page.route("http://faceauth.test/api/v1/auth/login/", async (route) => {
    await route.fulfill({
      json: { user_id: "user-1", tokens: { redirect_token: "once" } },
    });
  });

  await page.goto("/kiosk");
  await page.getByLabel("Token").fill("kiosk-token");
  await page.getByRole("button", { name: "Conectar" }).click();
  await expect(page.getByRole("heading", { name: "Principal" })).toBeVisible();
  await page.getByRole("button", { name: "Ingresar con rostro" }).click();
  await expect(page.getByText("Acceso concedido", { exact: true })).toBeVisible();
  const identify = ourBodies.find((body) => body.includes("redirect_token"));
  expect(identify).toContain("once");
  expect(identify).not.toContain("video");
});
