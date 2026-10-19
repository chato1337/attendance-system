export class FaceAuthRequestError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "FaceAuthRequestError";
    this.code = code;
    this.status = status;
  }
}

type ErrorBody = { code?: string; message?: string };

async function readError(response: Response): Promise<FaceAuthRequestError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    body = {};
  }
  const code = body.code || (response.status === 429 ? "rate_limited" : "request_failed");
  return new FaceAuthRequestError(
    code,
    body.message || "Face-Auth no completó la solicitud.",
    response.status,
  );
}

function root(apiUrl: string): string {
  return apiUrl.replace(/\/$/, "");
}

export async function loginFace(apiUrl: string, appId: string, video: Blob) {
  const form = new FormData();
  form.set("app_id", appId);
  form.set("video", video, video.type.includes("mp4") ? "clip.mp4" : "clip.webm");
  const response = await fetch(`${root(apiUrl)}/auth/login/`, {
    method: "POST",
    headers: { "X-App-Id": appId },
    body: form,
  });
  if (!response.ok) {
    throw await readError(response);
  }
  const data = (await response.json()) as {
    user_id?: string;
    tokens?: { redirect_token?: string };
  };
  const redirectToken = data.tokens?.redirect_token;
  if (!redirectToken) {
    throw new FaceAuthRequestError("invalid_token", "Face-Auth no entregó un token.", 502);
  }
  return { redirectToken, userId: data.user_id ?? "" };
}

export async function requestOtp(
  apiUrl: string,
  appId: string,
  person: { email: string; first_name: string; last_name: string },
) {
  const response = await fetch(`${root(apiUrl)}/otp/request/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-App-Id": appId },
    body: JSON.stringify({ app_id: appId, purpose: "email_verify", ...person }),
  });
  if (!response.ok) {
    throw await readError(response);
  }
}

export async function verifyOtp(apiUrl: string, appId: string, email: string, code: string) {
  const response = await fetch(`${root(apiUrl)}/otp/verify/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-App-Id": appId },
    body: JSON.stringify({ app_id: appId, purpose: "email_verify", email, code }),
  });
  if (!response.ok) {
    throw await readError(response);
  }
}

export async function registerFace(
  apiUrl: string,
  appId: string,
  person: { email: string; first_name: string; last_name: string },
  otpCode: string,
  video: Blob,
) {
  const form = new FormData();
  form.set("app_id", appId);
  form.set("email", person.email);
  form.set("first_name", person.first_name);
  form.set("last_name", person.last_name);
  form.set("otp_code", otpCode);
  form.set("video", video, video.type.includes("mp4") ? "clip.mp4" : "clip.webm");
  const response = await fetch(`${root(apiUrl)}/auth/register/`, {
    method: "POST",
    headers: { "X-App-Id": appId },
    body: form,
  });
  if (!response.ok) {
    throw await readError(response);
  }
  const data = (await response.json()) as { tokens?: { redirect_token?: string } };
  const redirectToken = data.tokens?.redirect_token;
  if (!redirectToken) {
    throw new FaceAuthRequestError("invalid_token", "Face-Auth no entregó un token.", 502);
  }
  return { redirectToken };
}
