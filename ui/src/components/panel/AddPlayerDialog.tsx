import { PanelAction } from './PanelAction';
import { useI18n } from '../../i18n/useI18n';

interface AddPlayerDialogProps {
  name: string;
  onChange: (name: string) => void;
  onAdd: () => void;
  onCancel: () => void;
}

export function AddPlayerDialog({ name, onChange, onAdd, onCancel }: AddPlayerDialogProps) {
  const { t } = useI18n();
  const canAdd = Boolean(name.trim());

  return (
    <div className="add-player-modal">
      <button
        type="button"
        className="add-player-modal__scrim"
        aria-label={t('picker.close', { title: t('menu.addPlayer') })}
        onClick={onCancel}
      />
      <div className="add-player-modal__dialog" role="dialog" aria-modal="true" aria-label={t('menu.addPlayer')}>
        <span id="add-player-title" className="add-player-modal__title">
          {t('menu.addPlayer')}
        </span>
        <input
          className="add-player-modal__input"
          type="text"
          autoFocus
          maxLength={40}
          placeholder={t('players.namePlaceholder')}
          value={name}
          aria-labelledby="add-player-title"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && canAdd) onAdd();
          }}
        />
        <div className="add-player-modal__actions">
          <PanelAction disabled={!canAdd} onClick={onAdd}>
            {t('menu.addPlayer')}
          </PanelAction>
          <PanelAction variant="secondary" onClick={onCancel}>
            {t('shutdown.cancel')}
          </PanelAction>
        </div>
      </div>
    </div>
  );
}
