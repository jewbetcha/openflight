import type { ReactNode } from 'react';
import type { ShotProcessingPhase } from '../stores/useShotStore';
import { ProgressIndicator } from './ProgressIndicator';
import './ShotProcessingArea.css';

interface ShotProcessingAreaProps {
  phase: ShotProcessingPhase | null;
  children: ReactNode;
}

export function ShotProcessingArea({ phase, children }: ShotProcessingAreaProps) {
  return (
    <>
      {phase ? (
        <div className="shot-processing-overlay">
          <div className="shot-processing-card">
            <ProgressIndicator
              variant="dialog"
              title={phase === 'capturing' ? 'Impact detected' : 'Shot captured'}
              detail={phase === 'capturing' ? 'Capturing radar data…' : 'Calculating metrics…'}
            />
          </div>
        </div>
      ) : null}
      {children}
    </>
  );
}
