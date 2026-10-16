import { useAuth } from "@/context/AuthContext";
import { useLocale, type Locale } from "@/context/LocaleContext";
import { useTheme, type Theme } from "@/context/ThemeContext";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { Tabs } from "@/components/ui/Tabs";
import { ContourField } from "@/components/layout/AmbientBackground";
import { Avatar } from "@/components/layout/AppShell";

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const { t, locale, setLocale } = useLocale();
  const { theme, setTheme } = useTheme();

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 stagger">
      <PageHeader title={t.profile.title} />

      <div className="relative overflow-hidden rounded-panel bg-grove-deep p-6 text-white shadow-elevate sm:p-8">
        <div className="absolute inset-0 text-sprout/[0.15]" aria-hidden="true">
          <ContourField variant="hero" />
        </div>
        <div className="relative flex items-center gap-5">
          <Avatar name={user?.full_name} size="lg" />
          <div className="min-w-0">
            <p className="text-sm text-white/60">{t.profile.account}</p>
            <p className="truncate font-display text-2xl font-semibold">{user?.full_name}</p>
            {user?.role && (
              <div className="mt-2">
                <Badge tone="primary" className="!bg-white/10 !text-white !ring-white/20">
                  {t.roles[user.role]}
                </Badge>
              </div>
            )}
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle icon="language">{t.profile.language}</CardTitle>
        </CardHeader>
        <Tabs
          tabs={[
            { key: "en", label: t.profile.english },
            { key: "ar", label: t.profile.arabic },
          ]}
          active={locale}
          onChange={(key) => setLocale(key as Locale)}
        />
      </Card>

      <Card>
        <CardHeader>
          <CardTitle icon={theme === "dark" ? "moon" : "sun"}>{t.common.theme}</CardTitle>
        </CardHeader>
        <Tabs
          tabs={[
            { key: "light", label: t.common.lightMode, icon: <Icon name="sun" className="h-4 w-4" /> },
            { key: "dark", label: t.common.darkMode, icon: <Icon name="moon" className="h-4 w-4" /> },
          ]}
          active={theme}
          onChange={(key) => setTheme(key as Theme)}
        />
      </Card>

      <Button variant="danger" size="lg" icon="logout" onClick={() => void logout()}>
        {t.nav.logout}
      </Button>
    </div>
  );
}
