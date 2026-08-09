import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const { t, locale, setLocale } = useLocale();

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6 animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.profile.title}</h1>

      <Card>
        <CardHeader>
          <CardTitle>{t.profile.account}</CardTitle>
        </CardHeader>
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-light text-lg font-semibold text-primary-dark">
            {user?.full_name?.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="font-display text-lg font-semibold text-ink">{user?.full_name}</p>
            <div className="mt-1">
              <Badge tone="primary">{user?.role}</Badge>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t.profile.language}</CardTitle>
        </CardHeader>
        <div className="flex gap-2.5">
          <Button variant={locale === "en" ? "primary" : "secondary"} onClick={() => setLocale("en")}>
            {t.profile.english}
          </Button>
          <Button variant={locale === "ar" ? "primary" : "secondary"} onClick={() => setLocale("ar")}>
            {t.profile.arabic}
          </Button>
        </div>
      </Card>

      <Button variant="danger" onClick={() => void logout()}>
        {t.nav.logout}
      </Button>
    </div>
  );
}
