import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useLanguage } from '../state/useLanguage';

interface PairPayload {
  v: 1;
  s: string;
  h: string;
  p: number;
}

type State = 'idle' | 'loading' | 'ready' | 'error';

export const PairingQR = memo(function PairingQR() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<State>('idle');
  const [error, setError] = useState('');
  const { t } = useLanguage();

  const generate = useCallback(async () => {
    setState('loading');
    setError('');

    let payload: PairPayload;
    try {
      const res = await fetch('/api/pair-qr', { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      payload = await res.json() as PairPayload;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pairing data');
      setState('error');
      return;
    }

    try {
      const QRCode: typeof import('qrcode') = await import('qrcode');
      const canvas = canvasRef.current;
      if (!canvas) { setError('Canvas not ready'); setState('error'); return; }
      await QRCode.toCanvas(canvas, JSON.stringify(payload), {
        width: 220,
        margin: 1,
        color: { dark: '#000000', light: '#ffffff' },
        errorCorrectionLevel: 'M',
      });
      setState('ready');
    } catch {
      setError('Failed to render QR code');
      setState('error');
    }
  }, []);

  useEffect(() => {
    // Capture at effect time - ref may be null in cleanup after unmount
    const canvas = canvasRef.current;
    return () => {
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
    };
  }, []);

  return (
    <div style={styles.root}>
      <p style={styles.label}>{t('pairMobileApp')}</p>
      <p style={styles.hint}>{t('pairMobileHint')}</p>
      {state === 'idle' && (
        <button type="button" style={styles.btn} onClick={generate}>
          {t('showPairingQR')}
        </button>
      )}
      {state === 'loading' && <p style={styles.sub}>{t('generating')}</p>}
      {state === 'error' && (
        <>
          <p style={{ ...styles.sub, color: '#ef4444' }}>{error}</p>
          <button type="button" style={styles.btn} onClick={generate}>
            {t('retry')}
          </button>
        </>
      )}
      <canvas
        ref={canvasRef}
        style={{
          display: state === 'ready' ? 'block' : 'none',
          margin: '12px auto 0',
          borderRadius: 8,
        }}
      />
      {state === 'ready' && (
        <button type="button" style={{ ...styles.btn, marginTop: 10 }} onClick={() => setState('idle')}>
          {t('hideQR')}
        </button>
      )}
    </div>
  );
});

// Sizes in rem so the card scales with the fluid root font-size across screens.
const styles: Record<string, React.CSSProperties> = {
  root: {
    background: 'var(--surface-1, #1a1a1a)',
    borderRadius: '0.625rem',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.5rem',
    border: '1px solid var(--line, #2a2a2a)',
  },
  label: {
    color: 'var(--text, #f5f5f5)',
    fontWeight: 700,
    fontSize: '0.875rem',
    margin: 0,
  },
  hint: {
    color: 'var(--sub, #888)',
    fontSize: '0.75rem',
    margin: 0,
    textAlign: 'center',
    lineHeight: 1.5,
    maxWidth: '17.5rem',
  },
  sub: {
    color: 'var(--sub, #888)',
    fontSize: '0.75rem',
    margin: 0,
  },
  btn: {
    background: 'var(--accent, #22c55e)',
    color: '#000',
    border: 'none',
    borderRadius: '0.5rem',
    padding: '0.625rem 1.25rem',
    fontWeight: 700,
    fontSize: '0.875rem',
    cursor: 'pointer',
    minHeight: 'var(--touch-min)',
  },
};
