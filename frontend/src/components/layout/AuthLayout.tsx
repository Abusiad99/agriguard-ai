import { Outlet } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";

export function AuthLayout() {
  const { t, locale, setLocale } = useLocale();

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-primary-dark p-10 text-white lg:flex">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
            </svg>
          </div>
          <span className="font-display text-xl font-semibold">{t.app.name}</span>
        </div>

        <div>
          <p className="font-display text-4xl font-medium leading-tight">{t.app.tagline}</p>
          <p className="mt-4 max-w-sm text-primary-light/90">
            Point your camera at a leaf. AgriGuard identifies the plant, diagnoses disease and pests,
            and tells you exactly what to do next — organic or chemical treatment, prevention, and
            weather-aware timing.
          </p>
        </div>

        <p className="text-sm text-primary-light/70">
          Supporting 17 crops, from tomato to date palm.
        </p>
      </div>

      <div className="flex flex-col justify-center px-6 py-12 sm:px-12 lg:px-16">
        <div className="mb-6 flex justify-end lg:hidden">
          <button
            onClick={() => setLocale(locale === "en" ? "ar" : "en")}
            className="rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-muted"
          >
            {locale === "en" ? "العربية" : "English"}
          </button>
        </div>
        <div className="mx-auto w-full max-w-sm">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
