import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { ApiError } from "@/types/api";
import { safeRedirectPath } from "@/lib/safeRedirect";
import { apiErrorText } from "@/lib/apiErrorText";

export default function LoginPage() {
  const { t, locale } = useLocale();
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
      const from = safeRedirectPath((location.state as { from?: Location } | null)?.from?.pathname);
      navigate(from, { replace: true });
    } catch (err) {
      // Wrong email/password gets the sign-in wording; anything else (too many attempts,
      // an invalid email address, no connection) says what actually happened.
      const wrongCredentials = err instanceof ApiError && err.code === "INVALID_CREDENTIALS";
      setError(wrongCredentials ? t.auth.loginError : apiErrorText(err, t, locale));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="stagger">
      <h1 className="font-display text-[1.75rem] font-semibold leading-tight text-ink">{t.auth.loginTitle}</h1>
      <p className="mt-2 text-[0.95rem] text-muted">{t.auth.loginSubtitle}</p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4" noValidate>
        {error && <Alert tone="error">{error}</Alert>}

        <Input
          label={t.auth.email}
          icon="mail"
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label={t.auth.password}
          icon="lock"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <Button type="submit" size="lg" fullWidth isLoading={isSubmitting} iconEnd="arrowRight" className="mt-3">
          {t.auth.loginButton}
        </Button>
      </form>

      <p className="mt-7 text-center text-sm text-muted">
        {t.auth.noAccount}{" "}
        <Link to="/register" className="font-semibold text-primary underline-offset-4 transition-colors hover:text-primary-dark hover:underline">
          {t.auth.signUp}
        </Link>
      </p>
    </div>
  );
}
