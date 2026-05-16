import { NextResponse } from 'next/server';

/**
 * Pass-through proxy to the FastAPI backend.
 *
 * Keeps the BACKEND_API_KEY (if set) server-side instead of leaking it to the
 * browser. Frontend code can hit either:
 *   - `/api/inspect`         → forwards to `POST {API_URL}/api/v1/inspect?mode=async`
 *   - `/api/inspect?sync=1`  → forwards to `POST {API_URL}/api/v1/inspect/sync`
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '');

export async function POST(req: Request) {
  const url = new URL(req.url);
  const sync = url.searchParams.get('sync') === '1';
  const target = `${API_URL}${sync ? '/api/v1/inspect/sync' : '/api/v1/inspect?mode=async'}`;

  const apiKey = process.env.BACKEND_API_KEY;
  const incoming = req.headers;

  const headers = new Headers();
  const ct = incoming.get('content-type');
  if (ct) headers.set('content-type', ct);
  if (apiKey) headers.set('x-api-key', apiKey);

  try {
    const upstream = await fetch(target, {
      method: 'POST',
      headers,
      body: req.body,
      // @ts-expect-error — duplex required for streaming bodies in Node fetch
      duplex: 'half',
    });

    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        'content-type':
          upstream.headers.get('content-type') ?? 'application/json',
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json(
      { detail: `Backend bağlantı hatası: ${message}` },
      { status: 502 },
    );
  }
}
