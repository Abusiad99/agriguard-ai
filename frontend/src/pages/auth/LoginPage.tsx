import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { ApiError } from "@/types/api";

export default function LoginPage() {
  const { t } = useLocale();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      const from = (location.state as { from?: Location })?.from?.pathname ?? "/dashboard";
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "INVALID_CREDENTIALS") {
        setError(t.auth.loginError);
      } else {
        setError(t.auth.genericError);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.auth.loginTitle}</h1>
      <p className="mt-1.5 text-sm text-muted">{t.auth.loginSubtitle}</p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4" noValidate>
        {error && <Alert tone="error">{error}</Alert>}

        <Input
          label={t.auth.email}
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label={t.auth.password}
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <Button type="submit" fullWidth isLoading={isSubmitting} className="mt-2">
          {t.auth.loginButton}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        {t.auth.noAccount}{" "}
        <Link to="/register" className="font-semibold text-primary hover:underline">
          {t.auth.signUp}
        </Link>
      </p>
    </div>
  );
}
