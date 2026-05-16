import { ImageResponse } from 'next/og';

// Route segment config
export const runtime = 'edge';
export const alt = 'Hasarİ — Yapay Zeka ile Araç Hasar Tespiti';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '72px 80px',
          background:
            'linear-gradient(135deg, #0b3aa8 0%, #1e6ee0 55%, #4c9fff 100%)',
          color: 'white',
          fontFamily: 'sans-serif',
          position: 'relative',
        }}
      >
        {/* Decorative blob */}
        <div
          style={{
            position: 'absolute',
            top: -180,
            right: -180,
            width: 600,
            height: 600,
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.08)',
            display: 'flex',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: -220,
            left: -160,
            width: 520,
            height: 520,
            borderRadius: '50%',
            background: 'rgba(0,0,0,0.12)',
            display: 'flex',
          }}
        />

        {/* Top: brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 20,
              background: 'white',
              color: '#1e6ee0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 44,
              fontWeight: 800,
              letterSpacing: -2,
            }}
          >
            H
          </div>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              lineHeight: 1.05,
            }}
          >
            <span style={{ fontSize: 44, fontWeight: 800, letterSpacing: -1 }}>
              Hasarİ
            </span>
            <span style={{ fontSize: 22, opacity: 0.85 }}>
              Yapay zeka destekli oto ekspertiz
            </span>
          </div>
        </div>

        {/* Center: headline */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
            maxWidth: 980,
          }}
        >
          <span
            style={{
              fontSize: 78,
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: -2,
            }}
          >
            Araç hasarını fotoğraftan tespit et.
          </span>
          <span style={{ fontSize: 32, opacity: 0.92, lineHeight: 1.3 }}>
            Parça bazlı rapor + TL bazlı onarım maliyet tahmini · saniyeler içinde
          </span>
        </div>

        {/* Bottom: features chips */}
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          {[
            '20+ parça',
            '6 hasar sınıfı',
            '< 8 sn analiz',
            'Türkiye fiyat tabanı',
          ].map((chip) => (
            <div
              key={chip}
              style={{
                display: 'flex',
                padding: '12px 22px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.18)',
                border: '1px solid rgba(255,255,255,0.35)',
                fontSize: 24,
                fontWeight: 600,
              }}
            >
              {chip}
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size },
  );
}
