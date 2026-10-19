export type Tokens = {
  access: string | null;
  refresh: string | null;
};

let tokens: Tokens = { access: null, refresh: null };
let tokenListener: ((next: Tokens) => void) | null = null;
let expiredHandler: (() => void) | null = null;

export function readTokens(): Tokens {
  return tokens;
}

export function writeTokens(next: Tokens): void {
  tokens = next;
  tokenListener?.(next);
}

export function setTokenListener(listener: (next: Tokens) => void): void {
  tokenListener = listener;
}

export function setSessionExpiredHandler(handler: () => void): void {
  expiredHandler = handler;
}

export function notifySessionExpired(): void {
  expiredHandler?.();
}
