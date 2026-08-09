import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import type { TranslationDict } from "@/i18n/en";

export type Locale = "en" | "ar";

const DICTIONARIES: Record<Locale, TranslationDict> = { en, ar };
const RTL_LOCALES: Locale[] = ["ar"];
const STORAGE_KEY = "agriguard_locale";

interface LocaleContextValue {
  locale: Locale;
  dir: "ltr" | "rtl";
  t: TranslationDict;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextValue | undefined>(undefined);

function detectInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored === "en" || stored === "ar") return stored;
  return navigator.language?.toLowerCase().startsWith("ar") ? "ar" : "en";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectInitialLocale);

  const dir = RTL_LOCALES.includes(locale) ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [locale, dir]);

  const setLocale = (next: Locale) => {
    localStorage.setItem(STORAGE_KEY, next);
    setLocaleState(next);
  };

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, dir, t: DICTIONARIES[locale], setLocale }),
    [locale, dir]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within a LocaleProvider");
  return ctx;
}
