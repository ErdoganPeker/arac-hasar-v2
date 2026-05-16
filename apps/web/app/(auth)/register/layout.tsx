import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Hesap Oluştur',
  description:
    'Birkaç saniyede ücretsiz Hasarİ hesabı oluştur. Yapay zeka destekli araç hasar tespitine hemen başla.',
  alternates: { canonical: '/register' },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: 'Hesap Oluştur · Hasarİ',
    description:
      'Ücretsiz hesap oluştur, fotoğrafla araç hasar tespitine başla.',
    url: '/register',
    type: 'website',
  },
};

export default function RegisterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
