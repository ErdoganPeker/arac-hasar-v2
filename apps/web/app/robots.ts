import type { MetadataRoute } from 'next';

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? 'https://hasari.app';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/api/',
          '/dashboard',
          '/dashboard/',
          '/admin',
          '/admin/',
          '/inspections/', // authenticated detail pages
          '/settings',
          '/settings/',
          '/_next/',
        ],
      },
      // Block aggressive AI scrapers that don't add SEO value (optional).
      {
        userAgent: ['GPTBot', 'CCBot', 'anthropic-ai', 'ClaudeBot'],
        allow: '/',
        // Comment out next two lines if you WANT to be indexed by LLM crawlers.
        // disallow: ['/'],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
