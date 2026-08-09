import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";

const ICONS = {
  dashboard: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
  ),
  scan: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
  ),
  history: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  ),
  profile: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
  ),
  admin: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
  ),
  logout: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 9V5.25A2.25 2.25 0 0110.5 3h6a2.25 2.25 0 012.25 2.25v13.5A2.25 2.25 0 0116.5 21h-6a2.25 2.25 0 01-2.25-2.25V15m-3 0l-3-3m0 0l3-3m-3 3H15" />
  ),
};

function Icon({ path, className = "h-5 w-5" }: { path: React.ReactNode; className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor" aria-hidden="true">
      {path}
    </svg>
  );
}

export function AppShell() {
  const { user, logout, hasRole } = useAuth();
  const { t, locale, setLocale } = useLocale();

  const navItems = [
    { to: "/dashboard", label: t.nav.dashboard, icon: ICONS.dashboard },
    { to: "/scan", label: t.nav.scan, icon: ICONS.scan },
    { to: "/history", label: t.nav.history, icon: ICONS.history },
    { to: "/profile", label: t.nav.profile, icon: ICONS.profile },
  ];
  if (hasRole("admin", "agronomist")) {
    navItems.push({ to: "/admin", label: t.nav.admin, icon: ICONS.admin });
  }

  const linkClasses = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-card px-3.5 py-2.5 text-sm font-medium transition-colors
     ${isActive ? "bg-primary-light text-primary-dark" : "text-muted hover:bg-canvas hover:text-ink"}`;

  return (
    <div className="min-h-screen bg-canvas">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 start-0 hidden w-64 flex-col border-e border-line bg-surface px-4 py-6 lg:flex">
        <div className="mb-8 flex items-center gap-2 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-white">
            <Icon path={ICONS.scan} className="h-5 w-5" />
          </div>
          <span className="font-display text-lg font-semibold text-ink">{t.app.name}</span>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClasses}>
              <Icon path={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex flex-col gap-3 border-t border-line pt-4">
          <button
            onClick={() => setLocale(locale === "en" ? "ar" : "en")}
            className="flex items-center gap-3 rounded-card px-3.5 py-2 text-sm font-medium text-muted hover:bg-canvas hover:text-ink"
          >
            <span className="flex h-5 w-5 items-center justify-center text-xs font-bold">
              {locale === "en" ? "AR" : "EN"}
            </span>
            {locale === "en" ? t.profile.arabic : t.profile.english}
          </button>
          <div className="flex items-center gap-3 px-3.5 py-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-light text-sm font-semibold text-primary-dark">
              {user?.full_name?.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{user?.full_name}</p>
              <p className="truncate text-xs capitalize text-muted">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={() => void logout()}
            className="flex items-center gap-3 rounded-card px-3.5 py-2.5 text-sm font-medium text-muted hover:bg-severity-severe-bg hover:text-severity-severe"
          >
            <Icon path={ICONS.logout} />
            {t.nav.logout}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:ps-64">
        <main className="mx-auto max-w-5xl px-4 py-6 pb-24 sm:px-6 sm:py-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface px-2 py-1.5 lg:hidden">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 rounded-card py-2 text-xs font-medium
               ${isActive ? "text-primary" : "text-muted"}`
            }
          >
            <Icon path={item.icon} className="h-6 w-6" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
