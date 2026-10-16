import { Link, Outlet, useLocation } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAuth } from "@/context/AuthContext";
import { Icon, type IconName } from "@/components/ui/Icon";
import { indicatorStyle, useSlidingIndicator } from "@/hooks/useSlidingIndicator";

export function AdminLayout() {
  const { t } = useLocale();
  const { hasRole } = useAuth();
  const { pathname } = useLocation();

  const tabs: { to: string; label: string; icon: IconName }[] = [
    { to: "/admin", label: t.admin.dashboardTitle, icon: "chart" },
    ...(hasRole("admin") ? [{ to: "/admin/users", label: t.admin.usersTitle, icon: "users" as IconName }] : []),
    { to: "/admin/diseases", label: t.admin.diseasesTitle, icon: "book" },
    { to: "/admin/treatments", label: t.admin.treatmentsTitle, icon: "beaker" },
  ];
  const activeTo = tabs.find((tab) => (tab.to === "/admin" ? pathname === "/admin" : pathname.startsWith(tab.to)))?.to;

  const { containerRef, rect } = useSlidingIndicator<HTMLElement>(activeTo);

  return (
    <div className="flex flex-col gap-8">
      <nav
        ref={containerRef}
        className="relative -mx-1 flex gap-1 overflow-x-auto rounded-2xl bg-ink/[0.05] p-1 ring-1 ring-inset ring-ink/[0.06] sm:mx-0 sm:self-start"
      >
        <span
          aria-hidden="true"
          className="absolute rounded-xl bg-surface shadow-soft ring-1 ring-ink/[0.06] transition-[transform,width,opacity] duration-500 ease-out-expo"
          style={indicatorStyle(rect)}
        />
        {tabs.map((tab) => {
          const isActive = tab.to === activeTo;
          return (
            <Link
              key={tab.to}
              to={tab.to}
              data-indicator-item
              data-active={isActive}
              aria-current={isActive ? "page" : undefined}
              className={`relative z-[1] flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-medium transition-colors duration-300
                ${isActive ? "text-primary-dark" : "text-muted hover:text-ink"}`}
            >
              <Icon name={tab.icon} className={`h-[18px] w-[18px] ${isActive ? "text-primary" : ""}`} />
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <div key={pathname} className="animate-fade-in">
        <Outlet />
      </div>
    </div>
  );
}
