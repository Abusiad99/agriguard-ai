import { Outlet } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Logo, LogoMark } from "@/components/ui/Logo";
import { ContourField } from "./AmbientBackground";
import { ScanIllustration } from "./ScanIllustration";
import { LocaleToggle, ThemeToggle } from "./Toggles";

export function AuthLayout() {
  const { t } = useLocale();

  const features: { icon: IconName; label: string }[] = [
    { icon: "sprout", label: t.auth.featureCrops },
    { icon: "rain", label: t.auth.featureWeather },
    { icon: "document", label: t.auth.featureReports },
  ];

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.08fr_1fr]">
      {/* ---------- Hero: the grove at night, with a live example scan ---------- */}
      <section className="relative m-3 hidden overflow-hidden rounded-[2rem] bg-grove-deep text-white shadow-elevate lg:flex lg:flex-col">
        <div className="absolute inset-0 text-sprout/[0.16] [mask-image:radial-gradient(ellipse_at_center,transparent_10%,black_75%)]">
          <ContourField variant="hero" />
        </div>
        <div className="grain absolute inset-0 [--grain-opacity:0.08]" aria-hidden="true" />
        <div className="absolute -start-24 top-1/3 h-80 w-80 rounded-full bg-sprout/20 blur-[100px]" aria-hidden="true" />

        <div className="relative flex flex-1 flex-col gap-8 p-10 xl:p-12">
          <Logo name={t.app.name} tone="light" className="animate-fade-in" />

          <div className="flex flex-1 items-center justify-center py-4">
            <div className="w-[14.5rem] animate-rise-in [animation-delay:250ms] xl:w-[16.5rem]">
              <ScanIllustration />
            </div>
          </div>

          <div className="max-w-lg animate-rise-in [animation-delay:120ms]">
            <h2 className="text-balance font-display text-[2.35rem] font-semibold leading-[1.12] xl:text-[2.75rem]">{t.app.tagline}</h2>
            <p className="mt-4 text-[1.02rem] leading-relaxed text-white/70">{t.auth.heroBody}</p>
          </div>

          <ul className="flex flex-wrap gap-2.5 animate-rise-in [animation-delay:450ms]">
            {features.map((f) => (
              <li
                key={f.label}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-white/85 backdrop-blur-md"
              >
                <Icon name={f.icon} className="h-4 w-4 text-sprout" />
                {f.label}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ---------- Form side ---------- */}
      <section className="relative flex flex-col px-5 py-6 sm:px-10 lg:px-14">
        <div className="flex items-center justify-between lg:justify-end">
          <span className="flex items-center gap-2.5 lg:hidden">
            <LogoMark className="h-9 w-9" />
            <span className="font-display text-base font-semibold text-ink">{t.app.name}</span>
          </span>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <LocaleToggle variant="pill" className="ms-1" />
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[26rem]">
            {/* Compact hero for small screens */}
            <div className="relative mb-8 overflow-hidden rounded-[1.75rem] bg-grove-deep p-6 text-white shadow-elevate lg:hidden">
              <div className="absolute inset-0 text-sprout/[0.18]">
                <ContourField variant="hero" />
              </div>
              <p className="relative text-balance font-display text-2xl font-semibold leading-snug">{t.app.tagline}</p>
              <p className="relative mt-2 text-sm text-white/70">{t.auth.heroCrops}</p>
            </div>

            <div className="glass rounded-[1.75rem] p-6 sm:p-8">
              <Outlet />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
