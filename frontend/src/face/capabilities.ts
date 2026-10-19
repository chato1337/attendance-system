const MIME_CANDIDATES = [
  "video/webm;codecs=vp8",
  "video/webm;codecs=vp9",
  "video/webm",
  "video/mp4",
];

export function captureMime(): string | null {
  if (typeof MediaRecorder === "undefined") {
    return null;
  }
  return (
    MIME_CANDIDATES.find((item) => {
      if (typeof MediaRecorder.isTypeSupported !== "function") {
        return item === "video/webm";
      }
      return MediaRecorder.isTypeSupported(item);
    }) ?? null
  );
}

export function captureCapabilities(): { ok: boolean; reason: string } {
  if (!navigator.mediaDevices?.getUserMedia) {
    return { ok: false, reason: "Este navegador no puede usar la cámara." };
  }
  if (!captureMime()) {
    return { ok: false, reason: "Este navegador no puede grabar video. Use el flujo alojado." };
  }
  return { ok: true, reason: "" };
}
