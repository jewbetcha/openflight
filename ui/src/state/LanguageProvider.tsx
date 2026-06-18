import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { LangCode, TKey } from '../i18n/translations';
import { t as translate } from '../i18n/translations';
import { LanguageContext } from './LanguageContext';

const LANG_KEY = 'openflight.language';
const VALID: LangCode[] = ['en','es','fr','de','pt','it','nl','sv','ja','ko','zh-hans','zh-hant','th','no','da','fi'];

/** BCP-47 tags so screen readers pick the right pronunciation voice. */
const BCP47: Record<LangCode, string> = {
  en: 'en', es: 'es', fr: 'fr', de: 'de', pt: 'pt', it: 'it', nl: 'nl', sv: 'sv',
  ja: 'ja', ko: 'ko', 'zh-hans': 'zh-Hans', 'zh-hant': 'zh-Hant', th: 'th',
  no: 'no', da: 'da', fi: 'fi',
};

function readLanguage(): LangCode {
  if (typeof window === 'undefined') return 'en';
  const v = window.localStorage.getItem(LANG_KEY) as LangCode;
  return VALID.includes(v) ? v : 'en';
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<LangCode>(readLanguage);

  const setLanguage = useCallback((code: LangCode) => {
    setLanguageState(code);
    window.localStorage.setItem(LANG_KEY, code);
  }, []);

  // Keep <html lang> in sync so VoiceOver / TalkBack pronounce text in the
  // selected language (they read our literal strings; they do not translate).
  useEffect(() => {
    document.documentElement.lang = BCP47[language];
  }, [language]);

  const t = useCallback((key: TKey) => translate(language, key), [language]);

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
