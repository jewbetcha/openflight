import { PanelAction } from './PanelAction';
import { useI18n } from '../../i18n/useI18n';

interface ClearSessionDialogProps {
  playerName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ClearSessionDialog({ playerName, onConfirm, onCancel }: ClearSessionDialogProps) {
  const { t } = useI18n();

  return (
    <div className="add-player-modal">
      <button
        type="button"
        className="add-player-modal__scrim"
        aria-label={t('clearSession.close')}
        onClick={onCancel}
      />
      <div
        className="add-player-modal__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="clear-session-title"
        aria-describedby="clear-session-detail"
      >
        <span id="clear-session-title" className="add-player-modal__title">
          {t('clearSession.confirm', { name: playerName })}
        </span>
        <p id="clear-session-detail" className="clear-session-dialog__detail">
          {t('clearSession.detail', { name: playerName })}
        </p>
        <div className="add-player-modal__actions">
          <PanelAction variant="danger" autoFocus onClick={onConfirm}>
            {t('app.clearSession')}
          </PanelAction>
          <PanelAction variant="secondary" onClick={onCancel}>
            {t('shutdown.cancel')}
          </PanelAction>
        </div>
      </div>
    </div>
  );
}
