import type { SessionStats, Shot } from '../types/shot';
import { useShotStore } from '../stores/useShotStore';
import { playSwingCapturedCue } from '../utils/audioCue';

export function handleShotMessage(data: { shot: Shot; stats: SessionStats }) {
  useShotStore.getState().addShot(data.shot);
  playSwingCapturedCue();
}
