import { FaceAuthRequestError } from "./faceAuthApi";

export function explainFaceError(error: unknown): { message: string; recaptureOnly: boolean } {
  if (!(error instanceof FaceAuthRequestError)) {
    return { message: "No hay conexión con el servicio facial.", recaptureOnly: false };
  }
  if (error.code === "no_match") {
    return {
      message: "Rostro no reconocido. Puede usar su tarjeta o registrarse.",
      recaptureOnly: false,
    };
  }
  if (
    error.code === "spoof_detected" ||
    error.code === "low_quality_capture" ||
    error.code === "face_not_found" ||
    error.code === "invalid_video"
  ) {
    return { message: error.message || "Vuelva a capturar el rostro.", recaptureOnly: true };
  }
  if (error.code === "rate_limited" || error.status === 429) {
    return {
      message: "Demasiados intentos. Espere un momento y vuelva a intentar.",
      recaptureOnly: false,
    };
  }
  if (error.code === "email_taken") {
    return { message: "Ese correo ya está registrado en Face-Auth.", recaptureOnly: false };
  }
  if (error.code === "duplicate_biometric") {
    return { message: "Ese rostro ya está enrolado. Intente ingresar.", recaptureOnly: false };
  }
  if (error.code === "app_inactive" || error.code === "app_not_found") {
    return {
      message: "La organización no está activa en Face-Auth. Avise al administrador.",
      recaptureOnly: false,
    };
  }
  if (error.code.startsWith("otp_")) {
    return { message: error.message || "El código no es válido.", recaptureOnly: false };
  }
  return { message: error.message, recaptureOnly: false };
}
