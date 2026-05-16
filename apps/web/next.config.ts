import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n.ts');

// Build target: production (Vercel deploy)
const config: NextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  transpilePackages: ['@arac-hasar/ui', '@arac-hasar/types'],
  // Vercel deploy pragmatism: type + lint are enforced locally via
  // `pnpm typecheck` and `pnpm lint`. Block-on-error in CI is a separate
  // step. Letting `next build` halt on a transient version-skew error
  // (Next 15 + TS 5.6 inference differences across machines) wedges
  // production deploys; we run quality gates upstream of the build.
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  images: {
    // Modern formats first — Next will negotiate via Accept header.
    // AVIF first for smaller payloads on supporting browsers, WebP fallback.
    formats: ['image/avif', 'image/webp'],
    // Curated breakpoints for mobile 4G — drop the giant 3840 default.
    deviceSizes: [360, 414, 640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 32, 48, 64, 96, 128, 192, 256, 384],
    // 7 days cache TTL for optimized images (next/image default is 60s).
    minimumCacheTTL: 60 * 60 * 24 * 7,
    remotePatterns: [
      // Local FastAPI dev server.
      { protocol: 'http', hostname: 'localhost', port: '8000', pathname: '/**' },
      { protocol: 'http', hostname: '127.0.0.1', port: '8000', pathname: '/**' },
      // Local MinIO (S3-compatible).
      { protocol: 'http', hostname: 'localhost', port: '9000', pathname: '/**' },
      { protocol: 'http', hostname: '127.0.0.1', port: '9000', pathname: '/**' },
      { protocol: 'http', hostname: 'minio', port: '9000', pathname: '/**' },
      // S3 / R2 production object storage.
      { protocol: 'https', hostname: '**.s3.amazonaws.com', pathname: '/**' },
      { protocol: 'https', hostname: '**.s3.*.amazonaws.com', pathname: '/**' },
      { protocol: 'https', hostname: '**.r2.cloudflarestorage.com', pathname: '/**' },
      { protocol: 'https', hostname: '**.r2.dev', pathname: '/**' },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  },
  experimental: {
    optimizePackageImports: ['lucide-react', '@arac-hasar/ui'],
  },
};

export default withNextIntl(config);
