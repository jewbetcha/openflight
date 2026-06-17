import { useContext } from 'react';
import { ViewModeContext } from './viewModeContext';

export function useViewMode() {
  const ctx = useContext(ViewModeContext);
  if (!ctx) throw new Error('useViewMode must be used within ViewModeProvider');
  return ctx;
}
