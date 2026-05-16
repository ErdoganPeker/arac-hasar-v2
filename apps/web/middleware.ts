import { NextResponse, type NextRequest } from 'next/server';
import { decodeJwt, isJwtExpired } from '@/lib/jwt';

const PROTECTED_PREFIXES = [
  '/dashboard',
  // /inspect public demo previously sent unauthenticated POST /api/v1/inspect
  // and backend returned 401 (silent redirect to /login). Backend requires
  // auth for every inspect call. Until a true anonymous demo endpoint
  // exists, /inspect is treated as auth-gated and surfaces a clear login
  // flow via the middleware redirect.
  '/inspect',
  '/inspect/new',
  '/settings',
  '/users',
];

const ADMIN_PREFIXES = ['/users'];

const PUBLIC_AUTH_ROUTES = new Set(['/login', '/register']);

const LOCALE_COOKIE = 'NEXT_LOCALE';
const LOCALES = new Set(['tr', 'en']);

const TOKEN_COOKIE = 'access_token';

function needsAuth(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

function needsAdmin(pathname: string): boolean {
  return ADMIN_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  // Locale negotiation hint: ensure NEXT_LOCALE cookie exists so the server
  // resolveLocale() in i18n.ts has a stable value.
  const localeCookie = req.cookies.get(LOCALE_COOKIE)?.value;
  let res = NextResponse.next();

  if (!localeCookie || !LOCALES.has(localeCookie)) {
    const accept = req.headers.get('accept-language') ?? '';
    const preferred = accept
      .split(',')
      .map((p) => {
        const first = p.split(';')[0] ?? '';
        return first.trim().toLowerCase().split('-')[0] ?? '';
      })
      .find((l) => LOCALES.has(l));
    res.cookies.set(LOCALE_COOKIE, preferred ?? 'tr', {
      path: '/',
      maxAge: 60 * 60 * 24 * 365,
      sameSite: 'lax',
    });
  }

  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  const tokenValid = !!token && !isJwtExpired(token, 5);

  // If user has a valid token and visits /login or /register, send them to dashboard.
  if (tokenValid && PUBLIC_AUTH_ROUTES.has(pathname)) {
    const url = req.nextUrl.clone();
    url.pathname = '/dashboard';
    url.search = '';
    return NextResponse.redirect(url);
  }

  if (needsAuth(pathname)) {
    if (!tokenValid) {
      const url = req.nextUrl.clone();
      url.pathname = '/login';
      url.searchParams.set('next', pathname + (search || ''));
      return NextResponse.redirect(url);
    }
    if (needsAdmin(pathname)) {
      const payload = token ? decodeJwt(token) : null;
      if (!payload || payload.role !== 'admin') {
        const url = req.nextUrl.clone();
        url.pathname = '/dashboard';
        url.searchParams.set('error', 'forbidden');
        return NextResponse.redirect(url);
      }
    }
  }

  return res;
}

export const config = {
  matcher: [
    // Run on everything except Next internals and static assets.
    '/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)',
  ],
};
