# @arac-hasar/web

Next.js 15 (App Router) frontend for the **Hasarİ** — araç hasar tespiti MVP.

## Stack

- Next.js 15 + React 18.3 + TypeScript (strict)
- Tailwind CSS 3.4 with shared preset from `@arac-hasar/ui`
- Shared UI components from `@arac-hasar/ui`
- Shared types from `@arac-hasar/types`
- `axios` for backend calls (FastAPI on `:8000`)

## Quick start

From the monorepo root:

```bash
pnpm install
pnpm --filter @arac-hasar/web dev
# or
pnpm dev:web
```

App will be available at <http://localhost:3000>.

Make sure the backend is running on `:8000`:

```bash
pnpm backend:dev
```

## Environment

Copy `.env.example` to `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
# BACKEND_API_KEY=dev-secret   # optional — used only by /api/inspect proxy
```

| Variable                | Required | Purpose                              |
| ----------------------- | -------- | ------------------------------------ |
| `NEXT_PUBLIC_API_URL`   | yes      | Base URL of the FastAPI backend      |
| `BACKEND_API_KEY`       | no       | Forwarded by `/api/inspect` (server) |

## Routes

| Path                | Description                                       |
| ------------------- | ------------------------------------------------- |
| `/`                 | Landing — value props + CTA                       |
| `/inspect`          | Multi-file upload + mode selection (sync / async) |
| `/results/[id]`     | Inspection result with polling + part-centric UI  |
| `/history`          | Past inspections grid (falls back to demo data)   |
| `/api/inspect`      | Optional pass-through to backend `POST /api/v1/inspect`   |

## Scripts

| Script              | Purpose             |
| ------------------- | ------------------- |
| `pnpm dev`          | Dev server (`:3000`) |
| `pnpm build`        | Production build    |
| `pnpm start`        | Run prod server     |
| `pnpm lint`         | ESLint              |
| `pnpm typecheck`    | `tsc --noEmit`      |

## Backend endpoints consumed

- `POST /api/v1/inspect` — multipart upload, returns `inspection_id` (queued)
- `POST /api/v1/inspect/sync` — inline (≤ 5 images)
- `GET  /api/v1/inspect/{id}` — status + result (polled every 2 s, max 60 s)
- `GET  /api/v1/inspect` — history list (paginated)
- `GET  /health` — liveness probe (`/healthz` kept as alias)

Contract: `packages/types/src/api.ts`. Full reference: [`docs/API_GUIDE.md`](../../docs/API_GUIDE.md).

## Folder layout

```
apps/web/
├─ app/
│  ├─ layout.tsx           Root layout (Header, Footer, Inter font)
│  ├─ globals.css          Tailwind + UI styles
│  ├─ page.tsx             Landing
│  ├─ inspect/page.tsx     Upload flow
│  ├─ results/[id]/page.tsx Result + polling
│  ├─ history/page.tsx     History grid
│  └─ api/inspect/route.ts Backend proxy
├─ components/             Web-only components
│  ├─ Header.tsx
│  ├─ Footer.tsx
│  ├─ PartList.tsx         Part-centric list (damaged sorted + clean)
│  └─ ResultsTabs.tsx      3 tabs (overview/parts/damages) + overlay
├─ lib/
│  ├─ api.ts               Typed axios wrappers
│  └─ use-inspection-polling.ts
├─ next.config.ts
├─ tailwind.config.ts
└─ tsconfig.json
```
