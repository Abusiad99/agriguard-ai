import { useLocale } from "@/context/LocaleContext";
import { ButtonLink } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/Logo";

export default function NotFoundPage() {
  const { t } = useLocale();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center stagger">
      <LogoMark className="h-12 w-12" />
      {/* An empty viewfinder: nothing here to scan. */}
      <div className="relative px-10 py-4">
        <svg viewBox="0 0 100 60" className="absolute inset-0 h-full w-full text-primary/50" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" preserveAspectRatio="none" aria-hidden="true">
          <path d="M2 14V6a4 4 0 014-4h8M86 2h8a4 4 0 014 4v8M98 46v8a4 4 0 01-4 4h-8M14 58H6a4 4 0 01-4-4v-8" vectorEffect="non-scaling-stroke" />
        </svg>
        <p className="font-display text-[5.5rem] font-semibold leading-none tracking-tight text-primary">404</p>
      </div>
      <div>
        <p className="font-display text-2xl font-semibold text-ink">{t.notFound.title}</p>
        <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-muted">{t.notFound.body}</p>
      </div>
      <ButtonLink to="/dashboard" size="lg" icon="dashboard">
        {t.notFound.action}
      </ButtonLink>
    </div>
  );
}
