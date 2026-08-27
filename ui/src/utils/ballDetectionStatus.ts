import { t } from '../i18n';
import type { CameraStatus } from '../stores/useCameraStore';

/** Plain-language ball-detection line for the header status menu and system sheet. */
export function ballDetectionStatusLabel(status: CameraStatus): string {
  if (!status.available) {
    return t('menu.unavailable');
  }
  if (!status.enabled) {
    return t('menu.off');
  }
  if (status.ball_detected) {
    return t('menu.ballPercent', { percent: Math.round(status.ball_confidence * 100) });
  }
  return t('menu.searching');
}
