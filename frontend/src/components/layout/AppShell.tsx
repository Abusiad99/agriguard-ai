import { useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { Icon, type IconName } from "@/components/ui/Icon";
import { LogoMark } from "@/components/ui/Logo";
import { indicatorStyle, useSlidingIndicator } from "@/hooks/useSlidingIndicator";
import { LocaleToggle, ThemeToggle } from "./Toggles";

interface NavItem {
  key: string;
  to: string;
  label: string;
  icon: IconName;
}

/** Which nav item owns the current URL (a diagnosis detail belongs to History). */
function activeKeyFor(pathname: string): string {
  if (pathname.startsWith("/diagnoses")) return "history";
  return pathname.split("/")[1] ?? "";
}

/** The four destinations in the mobile tab bar, around the raised Scan button. */
const MOBILE_LEFT = ["dashboard", "plants"];
const MOBILE_RIGHT = ["history", "assistant"];

export function AppShell() {
  const { user, logout, hasRole } = useAuth();
  const { t } = useLocale();
  const { pathname } = useLocation();
  const activeKey = activeKeyFor(pathname);

  const navItems: NavItem[] = [
    { key: "dashboard", to: "/dashboard", label: t.nav.dashboard, icon: "dashboard" },
    { key: "scan", to: "/scan", label: t.nav.scan, icon: "camera" },
    { key: "plants", to: "/plants", label: t.nav.plants, icon: "leaf" },
    { key: "history", to: "/history", label: t.nav.history, icon: "history" },
    { key: "assistant", to: "/assistant", label: t.nav.assistant, icon: "chat" },
    { key: "profile", to: "/profile", label: t.nav.profile, icon: "profile" },
  ];
  if (hasRole("admin", "agronomist")) {
    navItems.push({ key: "admin", to: "/admin", label: t.nav.admin, icon: "admin" });
  }

  // New page → start at the top (the shell itself stays mounted between routes).
  const section = pathname.split("/")[1];
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname]);

  const { containerRef, rect } = useSlidingIndicator<HTMLElement>(activeKey);
  const roleLabel = user?.role ? t.roles[user.role] : "";

  return (
    <div className="min-h-screen">
      {/* ---------- Desktop sidebar ---------- */}
      <aside className="glass fixed inset-y-3 start-3 z-30 hidden w-[17rem] flex-col rounded-[1.75rem] p-4 lg:flex">
        <Link to="/dashboard" className="mb-8 mt-1 flex items-center gap-3 rounded-2xl px-2 py-1">
          <LogoMark />
          <span className="font-display text-lg font-semibold tracking-tight text-ink">{t.app.name}</span>
        </Link>

        <nav ref={containerRef} className="relative flex flex-1 flex-col gap-1">
          {/* The active pill glides between items rather than blinking on/off. */}
          <span
            aria-hidden="true"
            className="absolute rounded-2xl bg-primary/10 ring-1 ring-inset ring-primary/15 transition-[transform,height,width,opacity] duration-500 ease-out-expo dark:bg-primary/[0.12]"
            style={indicatorStyle(rect)}
          >
            <span className="absolute inset-y-3 start-0 w-1 rounded-full bg-primary shadow-[0_0_12px_rgb(var(--c-primary))]" />
          </span>
          {navItems.map((item) => {
            const isActive = activeKey === item.key;
            return (
              <Link
                key={item.key}
                to={item.to}
                data-indicator-item
                data-active={isActive}
                aria-current={isActive ? "page" : undefined}
                className={`group relative z-[1] flex items-center gap-3 rounded-2xl px-3.5 py-3 text-[0.95rem] font-medium transition-colors duration-300
                  ${isActive ? "text-primary-dark" : "text-muted hover:text-ink"}`}
              >
                <Icon
                  name={item.icon}
                  className={`h-5 w-5 transition-transform duration-300 ease-spring group-hover:scale-110 ${isActive ? "text-primary" : ""}`}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 flex flex-col gap-3">
          <div className="flex items-center justify-between rounded-2xl bg-ink/[0.04] p-1">
            <ThemeToggle />
            <LocaleToggle />
            <button
              type="button"
              onClick={() => void logout()}
              aria-label={t.nav.logout}
              title={t.nav.logout}
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-muted transition-all duration-300 ease-spring hover:-translate-y-0.5 hover:bg-severity-severe-bg hover:text-severity-severe active:scale-90"
            >
              <Icon name="logout" className="flip-rtl h-5 w-5" />
            </button>
          </div>
          <Link to="/profile" className="flex items-center gap-3 rounded-2xl p-2 transition-colors hover:bg-ink/[0.04]">
            <Avatar name={user?.full_name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
              <p className="truncate text-xs text-muted">{roleLabel}</p>
            </div>
          </Link>
        </div>
      </aside>

      {/* ---------- Mobile top bar ---------- */}
      <header className="sticky top-0 z-30 px-3 pt-3 lg:hidden">
        <div className="glass flex h-14 items-center justify-between rounded-2xl ps-2 pe-1.5">
          <Link to="/dashboard" className="flex items-center gap-2.5">
            <LogoMark className="h-9 w-9" />
            <span className="font-display text-base font-semibold text-ink">{t.app.name}</span>
          </Link>
          <div className="flex items-center">
            <ThemeToggle />
            <LocaleToggle />
            <Link to="/profile" aria-label={t.nav.profile} className="ms-1 rounded-xl p-0.5">
              <Avatar name={user?.full_name} size="sm" />
            </Link>
          </div>
        </div>
      </header>

      {/* ---------- Main content ---------- */}
      <div className="lg:ps-[18.5rem]">
        <main className="mx-auto max-w-6xl px-4 pb-32 pt-6 sm:px-6 sm:pt-8 lg:px-10 lg:pb-12 lg:pt-10">
          <div key={section} className="animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>

      {/* ---------- Mobile bottom bar with a raised scan button ---------- */}
      <nav
        className="glass fixed inset-x-3 bottom-3 z-40 flex items-end justify-around rounded-[1.5rem] px-1 pb-2 pt-1.5 lg:hidden"
        style={{ marginBottom: "env(safe-area-inset-bottom)" }}
      >
        {navItems
          .filter((i) => MOBILE_LEFT.includes(i.key))
          .map((item) => (
            <MobileTab key={item.key} item={item} isActive={activeKey === item.key} />
          ))}
        <Link
          to="/scan"
          aria-label={t.nav.scan}
          aria-current={activeKey === "scan" ? "page" : undefined}
          className="group relative -mt-7 flex flex-1 flex-col items-center gap-1"
        >
          <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-brand text-white shadow-glow-lg ring-4 ring-canvas transition-transform duration-300 ease-spring group-active:scale-90">
            <span className="absolute inset-0 animate-pulse-ring rounded-full border-2 border-primary/50" />
            <Icon name="camera" className="h-6 w-6" />
          </span>
          <span className={`whitespace-nowrap text-[10.5px] font-semibold ${activeKey === "scan" ? "text-primary" : "text-muted"}`}>{t.nav.scan}</span>
        </Link>
        {navItems
          .filter((i) => MOBILE_RIGHT.includes(i.key))
          .map((item) => (
            <MobileTab key={item.key} item={item} isActive={activeKey === item.key} />
          ))}
      </nav>
    </div>
  );
}

function MobileTab({ item, isActive }: { item: NavItem; isActive: boolean }) {
  return (
    <Link
      to={item.to}
      aria-current={isActive ? "page" : undefined}
      className={`group relative flex min-w-0 flex-1 flex-col items-center gap-1 rounded-xl px-0.5 pt-2 text-[10.5px] font-medium transition-colors
        ${isActive ? "text-primary" : "text-muted"}`}
    >
      <span
        className={`flex h-8 w-12 items-center justify-center rounded-full transition-all duration-300 ease-spring group-active:scale-90
          ${isActive ? "bg-primary/15 scale-100" : "scale-95"}`}
      >
        <Icon name={item.icon} className="h-[22px] w-[22px]" />
      </span>
      <span className="whitespace-nowrap">{item.label}</span>
    </Link>
  );
}

export function Avatar({ name, size = "md" }: { name?: string | null; size?: "sm" | "md" | "lg" }) {
  const initials = (name ?? "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
  const dims = size === "lg" ? "h-16 w-16 text-xl rounded-[1.25rem]" : size === "sm" ? "h-9 w-9 text-xs rounded-xl" : "h-10 w-10 text-sm rounded-xl";
  return (
    <span className={`inline-flex shrink-0 items-center justify-center bg-brand font-display font-semibold text-white shadow-glow ${dims}`}>
      {initials}
    </span>
  );
}
