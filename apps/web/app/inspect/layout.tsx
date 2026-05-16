import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Yeni İnceleme — Fotoğrafla Hasar Tespiti',
  description:
    'Aracının fotoğraflarını yükle, parça bazlı hasar tespiti ve onarım maliyet tahminini saniyeler içinde al. Toplu yükleme, eş zamanlı veya asenkron analiz.',
  alternates: { canonical: '/inspect' },
  openGraph: {
    title: 'Yeni İnceleme · Hasarİ',
    description:
      'Fotoğraf yükle, parça bazlı hasar raporu ve onarım maliyet tahmini al.',
    url: '/inspect',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Yeni İnceleme · Hasarİ',
    description:
      'Fotoğraf yükle, parça bazlı hasar raporu ve onarım maliyet tahmini al.',
  },
};

export default function InspectLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
