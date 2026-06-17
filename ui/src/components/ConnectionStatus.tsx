import { useLanguage } from '../state/useLanguage';
import './ConnectionStatus.css';

interface ConnectionStatusProps {
  connected: boolean;
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  const { t } = useLanguage();
  return (
    <div
      className={`connection-status ${connected ? 'connection-status--connected' : 'connection-status--disconnected'}`}
    >
      <span className="connection-status__dot" />
      <span className="connection-status__text">{connected ? t('connected') : t('disconnected')}</span>
    </div>
  );
}
