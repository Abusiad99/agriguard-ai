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
import { PageHeader } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
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
    <div className="flex flex-col gap-6 stagger">
      <PageHeader title={t.admin.usersTitle} />

      <div className="max-w-md">
        <Input
          icon="search"
          placeholder={t.admin.searchUsers}
          aria-label={t.admin.searchUsers}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
      </div>

      {rowError && <Alert tone="error">{rowError}</Alert>}

      {users.status === "loading" && <PageLoader label={t.common.loading} />}
      {users.status === "error" && <ErrorState message={errorMessage(users.error)} onRetry={users.refetch} />}

      {users.status === "success" && (
        <div className="flex flex-col gap-5">
          <div className="glass overflow-x-auto rounded-panel">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-line/70">
                  <th className="px-5 py-4 text-start font-medium">{t.auth.fullName}</th>
                  <th className="px-5 py-4 text-start font-medium">{t.auth.email}</th>
                  <th className="px-5 py-4 text-start font-medium">{t.admin.role}</th>
                  <th className="px-5 py-4 text-start font-medium">{t.admin.status}</th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((u) => {
                  const isSelf = u.id === currentUser?.id;
                  const isSaving = savingUserId === u.id;
                  return (
                    <tr key={u.id} className="border-b border-line/50 transition-colors last:border-0 hover:bg-primary/[0.03]">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 font-display text-sm font-semibold text-primary">
                            {u.full_name.charAt(0).toUpperCase()}
                          </span>
                          <span className="whitespace-nowrap font-medium text-ink">{u.full_name}</span>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-muted">{u.email}</td>
                      <td className="px-5 py-3.5">
                        <div className="w-40">
                          <Select
                            compact
                            aria-label={t.admin.role}
                            value={u.role}
                            disabled={isSelf || isSaving}
                            onChange={(e) => void handleRoleChange(u.id, e.target.value as UserRole)}
                          >
                            <option value="farmer">{t.roles.farmer}</option>
                            <option value="agronomist">{t.roles.agronomist}</option>
                            <option value="admin">{t.roles.admin}</option>
                          </Select>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <button
                          type="button"
                          disabled={isSelf || isSaving}
                          onClick={() => void handleToggleActive(u.id, u.is_active)}
                          className="rounded-full transition-transform duration-300 ease-spring hover:scale-105 active:scale-95 disabled:pointer-events-none disabled:opacity-60"
                        >
                          <Badge tone={u.is_active ? "primary" : "severe"}>{u.is_active ? t.admin.active : t.admin.inactive}</Badge>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination page={page} totalPages={users.data.total_pages} onChange={setPage} />
        </div>
      )}
    </div>
  );
}
