import { NavLink, Outlet } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";

export function AdminLayout() {
  const { t } = useLocale();

  const tabs = [
    { to: "/admin", label: t.admin.dashboardTitle, end: true },
    { to: "/admin/users", label: t.admin.usersTitle, end: false },
    { to: "/admin/diseases", label: t.admin.diseasesTitle, end: false },
    { to: "/admin/treatments", label: t.admin.treatmentsTitle, end: false },
  ];

  return (
    <div className="flex flex-col gap-6">
      <nav className="flex gap-1 overflow-x-auto rounded-card border border-line bg-canvas p-1">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `whitespace-nowrap rounded-[calc(theme(borderRadius.card)-2px)] px-3.5 py-2 text-sm font-medium transition-colors
               ${isActive ? "bg-surface text-primary-dark shadow-sm" : "text-muted hover:text-ink"}`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
