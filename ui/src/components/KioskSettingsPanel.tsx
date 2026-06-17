import type { A11yPrefs } from '../state/useAccessibilitySettings';
import { useLanguage } from '../state/useLanguage';
import { A11yToggleRow, SettingsPanel } from './SettingsPanel';

interface Props {
  open: boolean;
  onClose: () => void;
  prefs: A11yPrefs;
  onToggle: (key: keyof A11yPrefs, value: boolean) => void;
  /** Nav-tab visibility toggles - kiosk/TV shell only (never the /display view). */
  showCameraTab: boolean;
  onToggleCameraTab: (visible: boolean) => void;
  showDebugTab: boolean;
  onToggleDebugTab: (visible: boolean) => void;
}

/**
 * SettingsPanel for the interactive kiosk/TV shell. Wraps the a11y-only base
 * panel and injects the Camera/Debug nav-tab toggles, which the passive
 * /display scoreboard has no use for. Keeps the tab-toggle contract explicit
 * and type-safe rather than threaded through optional props on the base.
 */
export function KioskSettingsPanel({
  open,
  onClose,
  prefs,
  onToggle,
  showCameraTab,
  onToggleCameraTab,
  showDebugTab,
  onToggleDebugTab,
}: Props) {
  const { t } = useLanguage();
  return (
    <SettingsPanel
      open={open}
      onClose={onClose}
      prefs={prefs}
      onToggle={onToggle}
      extraSections={
        <>
          <div className="a11y-panel__section-label">{t('cameraSection')}</div>
          <A11yToggleRow
            label={t('cameraTab')}
            sub={t('cameraTabSub')}
            checked={showCameraTab}
            onToggle={onToggleCameraTab}
          />
          <A11yToggleRow
            label={t('debugTab')}
            sub={t('debugTabSub')}
            checked={showDebugTab}
            onToggle={onToggleDebugTab}
            last
          />
        </>
      }
    />
  );
}
