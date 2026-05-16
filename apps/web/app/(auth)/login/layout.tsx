import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Giriş Yap',
  description:
    'Hasarİ hesabına giriş yap. Geçmiş incelemelerine eriş, yeni hasar raporları oluştur.',
  alternates: { canonical: '/login' },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: 'Giriş Yap · Hasarİ',
    description: 'Hasarİ hesabına giriş yap.',
    url: '/login',
    type: 'website',
  },
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
