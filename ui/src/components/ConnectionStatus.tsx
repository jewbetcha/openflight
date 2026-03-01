import './ConnectionStatus.css';

interface ConnectionStatusProps {
  connected: boolean;
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  return (
    <div
      className={`connection-status ${connected ? 'connection-status--connected' : 'connection-status--disconnected'}`}
    >
      <span className="connection-status__dot" />
      <span className="connection-status__text">{connected ? 'Connected' : 'Disconnected'}</span>
    </div>
  );
}
