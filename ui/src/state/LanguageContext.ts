import { createContext } from 'react';
import type { LangCode, TKey } from '../i18n/translations';

export interface LanguageContextValue {
  language: LangCode;
  setLanguage: (code: LangCode) => void;
  t: (key: TKey) => string;
}

export const LanguageContext = createContext<LanguageContextValue | null>(null);
