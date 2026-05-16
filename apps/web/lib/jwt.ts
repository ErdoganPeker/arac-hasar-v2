/**
 * Lightweight JWT decoder used for expiry checks ONLY.
 * Signature verification stays server-side. Never trust this for authorization.
 */

export interface JwtPayload {
  sub?: string;
  email?: string;
  role?: 'admin' | 'user' | string;
  exp?: number; // seconds since epoch
  iat?: number;
  [key: string]: unknown;
}

function base64UrlDecode(input: string): string {
  const pad = input.length % 4 === 0 ? '' : '='.repeat(4 - (input.length % 4));
  const b64 = (input + pad).replace(/-/g, '+').replace(/_/g, '/');
  if (typeof atob === 'function') {
    try {
      return decodeURIComponent(
        Array.prototype.map
          .call(atob(b64), (c: string) => {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
          })
          .join(''),
      );
    } catch {
      return atob(b64);
    }
  }
  // Node fallback (middleware / server)
  return Buffer.from(b64, 'base64').toString('utf8');
}

export function decodeJwt(token: string): JwtPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const segment = parts[1];
    if (!segment) return null;
    const payload = base64UrlDecode(segment);
    return JSON.parse(payload) as JwtPayload;
  } catch {
    return null;
  }
}

export function isJwtExpired(token: string, skewSeconds = 0): boolean {
  const payload = decodeJwt(token);
  if (!payload || typeof payload.exp !== 'number') return true;
  const nowSec = Math.floor(Date.now() / 1000);
  return payload.exp <= nowSec + skewSeconds;
}

export function getJwtRole(token: string): string | null {
  const payload = decodeJwt(token);
  if (!payload) return null;
  return (payload.role as string) ?? null;
}
