export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export interface PasswordCheck {
  valid: boolean;
  issues: string[];
}

/** Mirrors backend/app/application/services/auth_service.py::_validate_registration
 * so the frontend can give instant feedback before submitting. The backend remains
 * the source of truth / final validator (never trust client-side validation alone). */
export function checkPasswordStrength(password: string): PasswordCheck {
  const issues: string[] = [];
  if (password.length < 8) issues.push("At least 8 characters");
  if (!/[A-Z]/.test(password)) issues.push("At least one uppercase letter");
  if (!/[0-9]/.test(password)) issues.push("At least one number");
  return { valid: issues.length === 0, issues };
}

export const MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024;
export const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
