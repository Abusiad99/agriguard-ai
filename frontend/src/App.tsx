import { lazy, Suspense } from "react";
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
import ProfilePage from "@/pages/ProfilePage";
import AdminDashboardPage from "@/pages/admin/AdminDashboardPage";
import AdminUsersPage from "@/pages/admin/AdminUsersPage";
import AdminDiseasesPage from "@/pages/admin/AdminDiseasesPage";
import AdminTreatmentsPage from "@/pages/admin/AdminTreatmentsPage";
import AdminModelsPage from "@/pages/admin/AdminModelsPage";
import PlantsPage from "@/pages/plants/PlantsPage";
import PlantDetailPage from "@/pages/plants/PlantDetailPage";
import ReportsPage from "@/pages/reports/ReportsPage";
import ReportViewerPage from "@/pages/reports/ReportViewerPage";
import ReportComparePage from "@/pages/reports/ReportComparePage";
import SharedReportPage from "@/pages/reports/SharedReportPage";
import { PageLoader } from "@/components/ui/PageLoader";
import NotFoundPage from "@/pages/NotFoundPage";

// The map page pulls in Leaflet; load it on demand so it stays out of the main bundle.
const OutbreakPage = lazy(() => import("@/pages/OutbreakPage"));

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

              {/* Public read-only report links (no login; the token is the access check) */}
              <Route path="/shared/reports/:token" element={<SharedReportPage />} />

              {/* Authenticated routes */}
              <Route element={<ProtectedRoute />}>
                <Route element={<AppShell />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/scan" element={<ScanPage />} />
                  <Route path="/diagnoses/:id" element={<DiagnosisResultPage />} />
                  <Route path="/history" element={<HistoryPage />} />
                  <Route path="/profile" element={<ProfilePage />} />
                  <Route path="/plants" element={<PlantsPage />} />
                  <Route path="/plants/:id" element={<PlantDetailPage />} />
                  <Route path="/outbreak" element={<Suspense fallback={<PageLoader />}><OutbreakPage /></Suspense>} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/reports/compare" element={<ReportComparePage />} />
                  <Route path="/reports/:id" element={<ReportViewerPage />} />

                  {/* Admin / agronomist routes */}
                  <Route element={<RoleRoute roles={["admin", "agronomist"]} />}>
                    <Route path="/admin" element={<AdminLayout />}>
                      <Route index element={<AdminDashboardPage />} />
                      <Route path="users" element={<RoleRoute roles={["admin"]} />}>
                        <Route index element={<AdminUsersPage />} />
                      </Route>
                      <Route path="diseases" element={<AdminDiseasesPage />} />
                      <Route path="treatments" element={<AdminTreatmentsPage />} />
                      <Route path="models" element={<AdminModelsPage />} />
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
