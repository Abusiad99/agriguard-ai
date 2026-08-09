import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { ApiError } from "@/types/api";
import { checkPasswordStrength, isValidEmail } from "@/utils/validators";

export default function RegisterPage() {
  const { t } = useLocale();
  const { register } = useAuth();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (fullName.trim().length < 2) errors.full_name = t.common.required;
    if (!isValidEmail(email)) errors.email = t.auth.passwordHint;
    const pw = checkPasswordStrength(password);
    if (!pw.valid) errors.password = t.auth.passwordHint;
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setIsSubmitting(true);
    try {
      await register(email, password, fullName);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        const serverFieldErrors: Record<string, string> = {};
        for (const d of err.details) {
          if (d.field) serverFieldErrors[d.field] = d.issue;
        }
        if (Object.keys(serverFieldErrors).length > 0) {
          setFieldErrors(serverFieldErrors);
        } else {
          setFormError(err.message || t.auth.genericError);
        }
      } else {
        setFormError(t.auth.genericError);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.auth.registerTitle}</h1>
      <p className="mt-1.5 text-sm text-muted">{t.auth.registerSubtitle}</p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4" noValidate>
        {formError && <Alert tone="error">{formError}</Alert>}

        <Input
          label={t.auth.fullName}
          name="full_name"
          autoComplete="name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          error={fieldErrors.full_name}
        />
        <Input
          label={t.auth.email}
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
        />
        <Input
          label={t.auth.password}
          type="password"
          name="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          hint={!fieldErrors.password ? t.auth.passwordHint : undefined}
        />

        <Button type="submit" fullWidth isLoading={isSubmitting} className="mt-2">
          {t.auth.registerButton}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        {t.auth.haveAccount}{" "}
        <Link to="/login" className="font-semibold text-primary hover:underline">
          {t.auth.signIn}
        </Link>
      </p>
    </div>
  );
}
