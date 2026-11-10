import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import arabic from "./ar.json";

type Locale = "ar" | "en";
export function translateMessage(message: string, locale: Locale): string {
  return locale === "ar"
    ? ((arabic as Record<string, string>)[message] ?? message)
    : message;
}
const I18n = createContext<{
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (message: string) => string;
}>({
  locale: "ar",
  setLocale: () => {},
  t: (message) => message,
});
export function I18nProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocale] = useState<Locale>(() => {
    if (initialLocale) return initialLocale;
    try {
      return localStorage.getItem("polylingo-locale") === "en" ? "en" : "ar";
    } catch {
      return "ar";
    }
  });
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    document.title =
      "PolyLingo AI · " + translateMessage("Multilingual translation", locale);
    try {
      localStorage.setItem("polylingo-locale", locale);
    } catch {}
  }, [locale]);
  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: (message: string) => translateMessage(message, locale),
    }),
    [locale],
  );
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}
export function useI18n() {
  return useContext(I18n);
}
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className="locale-switch"
      role="group"
      aria-label={t("Interface language")}
      dir="ltr"
    >
      <button
        type="button"
        lang="ar"
        aria-pressed={locale === "ar"}
        onClick={() => setLocale("ar")}
      >
        العربية
      </button>
      <button
        type="button"
        lang="en"
        aria-pressed={locale === "en"}
        onClick={() => setLocale("en")}
      >
        English
      </button>
    </div>
  );
}
