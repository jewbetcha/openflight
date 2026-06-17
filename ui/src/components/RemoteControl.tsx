import { useLanguage } from '../state/useLanguage';
import './RemoteControl.css';

type RemoteKey = 'up' | 'down' | 'left' | 'right' | 'ok' | 'back';

interface RemoteControlProps {
  /** Relays a key to the display over the WebSocket (useSocket.sendRemoteKey). */
  sendKey: (key: RemoteKey) => void;
  connected: boolean;
}

/**
 * Phone/tablet web-remote (the /remote route). A big-touch D-pad whose buttons
 * relay nav keys over the existing Socket.IO connection to the TV/display,
 * which moves focus via the shared spatial-navigation engine. Brand- and
 * hardware-independent fallback - works with any TV when CEC/IR don't.
 */
export function RemoteControl({ sendKey, connected }: RemoteControlProps) {
  const { t } = useLanguage();
  // Disable the controls while offline so mashed presses aren't buffered by
  // Socket.IO and replayed as a stale burst on reconnect.
  const off = !connected;
  return (
    <main className="remote">
      <h1 className="sr-only">{`OpenFlight ${t('remoteTitle')}`}</h1>
      <div className={`remote__status ${connected ? 'remote__status--ok' : 'remote__status--off'}`} role="status">
        {connected ? t('remoteConnected') : t('remoteConnecting')}
      </div>

      <div className="remote__dpad" role="group" aria-label={t('a11yDpad')}>
        <button className="remote__btn remote__btn--up" onClick={() => sendKey('up')} aria-label={t('a11yUp')} disabled={off}>▲</button>
        <button className="remote__btn remote__btn--left" onClick={() => sendKey('left')} aria-label={t('a11yLeft')} disabled={off}>◀</button>
        <button className="remote__btn remote__btn--ok" onClick={() => sendKey('ok')} aria-label={t('a11ySelect')} disabled={off}>OK</button>
        <button className="remote__btn remote__btn--right" onClick={() => sendKey('right')} aria-label={t('a11yRight')} disabled={off}>▶</button>
        <button className="remote__btn remote__btn--down" onClick={() => sendKey('down')} aria-label={t('a11yDown')} disabled={off}>▼</button>
      </div>

      <button className="remote__back" onClick={() => sendKey('back')} disabled={off}>{t('remoteBack')}</button>

      <p className="remote__hint">{t('remoteHint')}</p>
    </main>
  );
}
