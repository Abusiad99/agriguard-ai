import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import type { UserRole } from "@/types/api";

export function RoleRoute({ roles }: { roles: UserRole[] }) {
  const { hasRole } = useAuth();

  if (!hasRole(...roles)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}
