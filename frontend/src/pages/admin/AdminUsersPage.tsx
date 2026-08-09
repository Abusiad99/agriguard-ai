import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { adminApi } from "@/lib/endpoints/admin";
import { useAuth } from "@/context/AuthContext";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import type { UserRole } from "@/types/api";
import { ApiError } from "@/types/api";

const PAGE_SIZE = 15;

export default function AdminUsersPage() {
  const { t } = useLocale();
  const { user: currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const users = useAsync(
    () => adminApi.listUsers({ search: search || undefined, page, page_size: PAGE_SIZE }),
    [search, page]
  );

  const handleRoleChange = async (userId: string, role: UserRole) => {
    setRowError(null);
    setSavingUserId(userId);
    try {
      await adminApi.updateUser(userId, { role });
      users.refetch();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setSavingUserId(null);
    }
  };

  const handleToggleActive = async (userId: string, isActive: boolean) => {
    setRowError(null);
    setSavingUserId(userId);
    try {
      await adminApi.updateUser(userId, { is_active: !isActive });
      users.refetch();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setSavingUserId(null);
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.admin.usersTitle}</h1>

      <Input
        placeholder={t.admin.searchUsers}
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />

      {rowError && <Alert tone="error">{rowError}</Alert>}

      {users.status === "loading" && <PageLoader label={t.common.loading} />}
      {users.status === "error" && <ErrorState message={errorMessage(users.error)} onRetry={users.refetch} />}

      {users.status === "success" && (
        <div className="overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-start text-sm">
            <thead className="border-b border-line bg-canvas text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 text-start">{t.auth.fullName}</th>
                <th className="px-4 py-3 text-start">{t.auth.email}</th>
                <th className="px-4 py-3 text-start">{t.admin.role}</th>
                <th className="px-4 py-3 text-start">{t.admin.status}</th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((u) => {
                const isSelf = u.id === currentUser?.id;
                return (
                  <tr key={u.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 font-medium text-ink">{u.full_name}</td>
                    <td className="px-4 py-3 text-muted">{u.email}</td>
                    <td className="px-4 py-3">
                      <Select
                        aria-label={t.admin.role}
                        value={u.role}
                        disabled={isSelf || savingUserId === u.id}
                        onChange={(e) => void handleRoleChange(u.id, e.target.value as UserRole)}
                        className="w-32"
                      >
                        <option value="farmer">farmer</option>
                        <option value="agronomist">agronomist</option>
                        <option value="admin">admin</option>
                      </Select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        disabled={isSelf || savingUserId === u.id}
                        onClick={() => void handleToggleActive(u.id, u.is_active)}
                        className="disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Badge tone={u.is_active ? "primary" : "severe"}>
                          {u.is_active ? t.admin.active : t.admin.inactive}
                        </Badge>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {users.data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3 border-t border-line py-3">
              <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t.common.back}
              </Button>
              <span className="text-sm text-muted">
                {t.common.page} {users.data.page} {t.common.of} {users.data.total_pages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page >= users.data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t.common.next}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
