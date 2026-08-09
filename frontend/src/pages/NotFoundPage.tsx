import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <p className="font-display text-5xl font-semibold text-primary">404</p>
      <p className="font-display text-lg font-semibold text-ink">Page not found</p>
      <p className="max-w-xs text-sm text-muted">The page you're looking for doesn't exist or has moved.</p>
      <Link to="/dashboard">
        <Button className="mt-2">Go to Dashboard</Button>
      </Link>
    </div>
  );
}
