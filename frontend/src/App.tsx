import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { LocaleProvider } from "@/context/LocaleContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { GuestRoute } from "@/routes/GuestRoute";
import { RoleRoute } from "@/routes/RoleRoute";
import { AppShell } from "@/components/layout/AppShell";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { AmbientBackground } from "@/components/layout/AmbientBackground";

import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import DashboardPage from "@/pages/DashboardPage";
import ScanPage from "@/pages/ScanPage";
import DiagnosisResultPage from "@/pages/DiagnosisResultPage";
import HistoryPage from "@/pages/HistoryPage";
import PlantsPage from "@/pages/PlantsPage";
import PlantDetailPage from "@/pages/PlantDetailPage";
import ComparePage from "@/pages/ComparePage";
import AssistantPage from "@/pages/AssistantPage";
import ProfilePage from "@/pages/ProfilePage";
import AdminDashboardPage from "@/pages/admin/AdminDashboardPage";
import AdminUsersPage from "@/pages/admin/AdminUsersPage";
import AdminDiseasesPage from "@/pages/admin/AdminDiseasesPage";
import AdminTreatmentsPage from "@/pages/admin/AdminTreatmentsPage";
import NotFoundPage from "@/pages/NotFoundPage";

export default function App() {
  return (
    <ThemeProvider>
      <LocaleProvider>
        <AmbientBackground />
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              {/* Public / guest-only routes */}
              <Route element={<GuestRoute />}>
                <Route element={<AuthLayout />}>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                </Route>
              </Route>

              {/* Authenticated routes */}
              <Route element={<ProtectedRoute />}>
                <Route element={<AppShell />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/scan" element={<ScanPage />} />
                  <Route path="/diagnoses/:id" element={<DiagnosisResultPage />} />
                  <Route path="/history" element={<HistoryPage />} />
                  <Route path="/plants" element={<PlantsPage />} />
                  <Route path="/plants/:id" element={<PlantDetailPage />} />
                  <Route path="/plants/:id/compare" element={<ComparePage />} />
                  <Route path="/assistant" element={<AssistantPage />} />
                  <Route path="/profile" element={<ProfilePage />} />

                  {/* Admin / agronomist routes */}
                  <Route element={<RoleRoute roles={["admin", "agronomist"]} />}>
                    <Route path="/admin" element={<AdminLayout />}>
                      <Route index element={<AdminDashboardPage />} />
                      <Route path="users" element={<RoleRoute roles={["admin"]} />}>
                        <Route index element={<AdminUsersPage />} />
                      </Route>
                      <Route path="diseases" element={<AdminDiseasesPage />} />
                      <Route path="treatments" element={<AdminTreatmentsPage />} />
                    </Route>
                  </Route>
                </Route>
              </Route>

              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </LocaleProvider>
    </ThemeProvider>
  );
}
