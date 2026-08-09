import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { PageLoader } from "@/components/ui/PageLoader";

/** Redirects an already-authenticated user away from /login and /register. */
export function GuestRoute() {
  const { isAuthenticated, isInitializing } = useAuth();

  if (isInitializing) return <PageLoader />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  return <Outlet />;
}
