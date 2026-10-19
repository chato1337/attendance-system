import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui";

import { captureCapabilities, captureMime } from "./capabilities";

const MAX_BYTES = 15 * 1024 * 1024;

type Props = {
  disabled?: boolean;
  durationMs?: number;
  onClip: (clip: Blob) => Promise<void> | void;
  onUnsupported?: () => void;
};

export function FaceCapture({ disabled = false, durationMs = 3000, onClip, onUnsupported }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [support] = useState(captureCapabilities);
  const [previewReady, setPreviewReady] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!support.ok) {
      return;
    }
    let active = true;
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (video) {
          try {
            video.srcObject = stream;
          } catch {
            video.removeAttribute("src");
          }
        }
        setPreviewReady(true);
      })
      .catch(() => {
        if (active) {
          setError("No se pudo abrir la cámara. Revise el permiso del navegador.");
        }
      });
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [support.ok]);

  async function record() {
    const stream = streamRef.current;
    const mime = captureMime();
    if (!stream || !mime || recording) {
      return;
    }
    setError("");
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data);
      }
    };
    const stopped = new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: mime }));
    });
    setRecording(true);
    recorder.start();
    window.setTimeout(() => {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    }, durationMs);
    const clip = await stopped;
    setRecording(false);
    const width = videoRef.current?.videoWidth ?? 0;
    const height = videoRef.current?.videoHeight ?? 0;
    if (width > 0 && height > 0 && (width < 320 || height < 240)) {
      setError("La cámara no alcanza la resolución mínima de 320×240.");
      return;
    }
    if (clip.size > MAX_BYTES) {
      setError("El clip supera 15 MB. Acérquese y vuelva a grabar.");
      return;
    }
    if (clip.size === 0) {
      setError("No se grabó video. Vuelva a intentarlo.");
      return;
    }
    await onClip(clip);
  }

  if (!support.ok) {
    return (
      <div className="face-unsupported">
        <p>{support.reason}</p>
        {onUnsupported ? (
          <Button type="button" onClick={onUnsupported}>
            Continuar en Face-Auth
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="face-capture">
      <div className="face-frame">
        <video ref={videoRef} autoPlay muted playsInline />
        <span className="face-oval" />
      </div>
      <p className="face-hint">Centre el rostro en el óvalo, con luz de frente, y parpadee.</p>
      {error ? <p className="face-error">{error}</p> : null}
      <Button
        type="button"
        onClick={() => void record()}
        disabled={disabled || !previewReady || recording}
      >
        {recording ? "Grabando…" : "Ingresar con rostro"}
      </Button>
    </div>
  );
}
