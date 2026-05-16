import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { AuthProvider } from '@/lib/auth-context';
import { ToastProvider } from '@/components/ToastProvider';
import './globals.css';

const inter = Inter({
  subsets: ['latin', 'latin-ext'],
  display: 'swap',
  variable: '--font-inter',
});

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? 'https://hasari.app';
const SITE_NAME = 'Hasarİ';
const DEFAULT_TITLE_TR = 'Hasarİ — Yapay Zeka ile Araç Hasar Tespiti';
const DEFAULT_DESCRIPTION_TR =
  'Yapay zeka destekli araç hasar tespiti. Fotoğraf yükle, parça bazlı hasar raporu ve onarım maliyet tahmini saniyeler içinde. Eksper ücreti yok, bekleme yok.';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: DEFAULT_TITLE_TR,
    template: `%s · ${SITE_NAME}`,
  },
  description: DEFAULT_DESCRIPTION_TR,
  applicationName: SITE_NAME,
  generator: 'Next.js',
  referrer: 'origin-when-cross-origin',
  keywords: [
    'araç hasar tespit',
    'yapay zeka oto ekspertiz',
    'hasar fiyat hesaplama',
    'fotoğrafla hasar tespiti',
    'kasko hasar tahmin',
    'oto ekspertiz online',
    'tampon çizik tamir fiyatı',
    'göçük tamir maliyeti',
    'AI car damage detection',
    'vehicle damage estimate',
  ],
  authors: [{ name: SITE_NAME, url: SITE_URL }],
  creator: SITE_NAME,
  publisher: SITE_NAME,
  category: 'technology',
  alternates: {
    canonical: '/',
    languages: {
      'tr-TR': '/',
      'en-US': '/',
      'x-default': '/',
    },
  },
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    title: DEFAULT_TITLE_TR,
    description: DEFAULT_DESCRIPTION_TR,
    url: SITE_URL,
    locale: 'tr_TR',
    alternateLocale: ['en_US'],
    images: [
      {
        url: '/opengraph-image',
        width: 1200,
        height: 630,
        alt: 'Hasarİ — Yapay Zeka ile Araç Hasar Tespiti',
        type: 'image/png',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: DEFAULT_TITLE_TR,
    description: DEFAULT_DESCRIPTION_TR,
    images: ['/opengraph-image'],
    creator: '@hasari_app',
  },
  robots: {
    index: true,
    follow: true,
    nocache: false,
    googleBot: {
      index: true,
      follow: true,
      noimageindex: false,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  icons: {
    icon: '/favicon.ico',
    shortcut: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
  formatDetection: {
    email: false,
    telephone: false,
    address: false,
  },
  verification: {
    // Replace with real codes after Search Console / Bing verification.
    // google: 'TODO_GOOGLE_SITE_VERIFICATION',
    // other: { 'msvalidate.01': 'TODO_BING_VERIFICATION' },
  },
};

export const viewport: Viewport = {
  themeColor: '#1e6ee0',
  width: 'device-width',
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  // Schema.org WebApplication JSON-LD (bilingual via inLanguage array).
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${SITE_URL}#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        logo: `${SITE_URL}/icon.png`,
        sameAs: [],
      },
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: DEFAULT_DESCRIPTION_TR,
        publisher: { '@id': `${SITE_URL}#organization` },
        inLanguage: ['tr-TR', 'en-US'],
      },
      {
        '@type': 'WebApplication',
        '@id': `${SITE_URL}#webapp`,
        name: SITE_NAME,
        url: SITE_URL,
        applicationCategory: 'BusinessApplication',
        applicationSubCategory: 'Automotive Damage Assessment',
        operatingSystem: 'Web, iOS, Android, Windows',
        browserRequirements: 'Requires JavaScript. Modern browser recommended.',
        description: DEFAULT_DESCRIPTION_TR,
        inLanguage: ['tr-TR', 'en-US'],
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'TRY',
        },
        featureList: [
          'Parça bazlı hasar tespiti',
          'Onarım maliyet tahmini (TL)',
          'Çoklu fotoğraf analizi',
          'Asenkron toplu işlem',
          'Türkiye yedek parça fiyat tabanı',
        ],
        aggregateRating: undefined,
        publisher: { '@id': `${SITE_URL}#organization` },
      },
    ],
  };

  return (
    <html lang={locale} className={inter.variable}>
      <body className="min-h-screen font-sans">
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <NextIntlClientProvider locale={locale} messages={messages}>
          <AuthProvider>
            <ToastProvider>
              <div className="flex min-h-screen flex-col">
                <Header />
                <main className="flex-1">{children}</main>
                <Footer />
              </div>
            </ToastProvider>
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
