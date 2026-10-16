import { useTheme } from "@/context/ThemeContext";
import { useLocale } from "@/context/LocaleContext";
import { Icon } from "@/components/ui/Icon";

const ROUND_BTN =
  "relative inline-flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl text-muted transition-all duration-300 ease-spring " +
  "hover:-translate-y-0.5 hover:bg-ink/[0.06] hover:text-ink active:scale-90";

/** Sun/moon swap: the outgoing icon spins away as the incoming one rises in. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const isDark = theme === "dark";
  return (
    <button type="button" onClick={toggleTheme} aria-label={t.common.toggleTheme} title={isDark ? t.common.lightMode : t.common.darkMode} className={`${ROUND_BTN} ${className}`}>
      <span className={`absolute transition-all duration-500 ease-spring ${isDark ? "rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"}`}>
        <Icon name="moon" className="h-5 w-5" />
      </span>
      <span className={`absolute transition-all duration-500 ease-spring ${isDark ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-0 opacity-0"}`}>
        <Icon name="sun" className="h-5 w-5" />
      </span>
    </button>
  );
}

export function LocaleToggle({ className = "", variant = "icon" }: { className?: string; variant?: "icon" | "pill" }) {
  const { locale, setLocale } = useLocale();
  const next = locale === "en" ? "ar" : "en";
  const label = locale === "en" ? "العربية" : "English";

  if (variant === "pill") {
    return (
      <button
        type="button"
        onClick={() => setLocale(next)}
        lang={next}
        className={`glass inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium text-ink transition-all duration-300 ease-spring hover:-translate-y-0.5 hover:text-primary-dark active:scale-95 ${className}`}
      >
        <Icon name="language" className="h-4 w-4" />
        {label}
      </button>
    );
  }

  return (
    <button type="button" onClick={() => setLocale(next)} aria-label={label} title={label} lang={next} className={`${ROUND_BTN} ${className}`}>
      <span className={`font-display font-semibold ${locale === "en" ? "text-base" : "text-[13px]"}`}>{locale === "en" ? "ع" : "EN"}</span>
    </button>
  );
}
