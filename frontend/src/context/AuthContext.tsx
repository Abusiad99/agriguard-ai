import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { authApi } from "@/lib/endpoints/auth";
import { tokenStorage } from "@/lib/tokenStorage";
import type { UserRole, UserSummary } from "@/types/api";

interface AuthContextValue {
  user: UserSummary | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const USER_STORAGE_KEY = "agriguard_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);

  // On mount: if a refresh token exists, silently restore the session by
  // exchanging it for a fresh access token, rather than forcing a re-login on
  // every page reload.
  useEffect(() => {
    const restore = async () => {
      const refreshToken = tokenStorage.getRefreshToken();
      const cachedUser = localStorage.getItem(USER_STORAGE_KEY);

      if (!refreshToken || !cachedUser) {
        setIsInitializing(false);
        return;
      }

      try {
        const tokens = await authApi.refresh({ refresh_token: refreshToken });
        tokenStorage.setAccessToken(tokens.access_token);
        tokenStorage.setRefreshToken(tokens.refresh_token);
        setUser(tokens.user);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(tokens.user));
      } catch {
        tokenStorage.clear();
        localStorage.removeItem(USER_STORAGE_KEY);
      } finally {
        setIsInitializing(false);
      }
    };
    void restore();
  }, []);

  const login = async (email: string, password: string) => {
    const tokens = await authApi.login({ email, password });
    tokenStorage.setAccessToken(tokens.access_token);
    tokenStorage.setRefreshToken(tokens.refresh_token);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(tokens.user));
    setUser(tokens.user);
  };

  const register = async (email: string, password: string, fullName: string) => {
    await authApi.register({ email, password, full_name: fullName });
    await login(email, password);
  };

  const logout = async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    try {
      if (refreshToken) await authApi.logout({ refresh_token: refreshToken });
    } catch {
      // Even if the network call fails, always clear local state so the user
      // isn't stuck "logged in" on their own device.
    } finally {
      tokenStorage.clear();
      localStorage.removeItem(USER_STORAGE_KEY);
      setUser(null);
    }
  };

  const hasRole = (...roles: UserRole[]) => (user ? roles.includes(user.role) : false);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: !!user, isInitializing, login, register, logout, hasRole }),
    [user, isInitializing]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
