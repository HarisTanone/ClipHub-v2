import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { AppLayout } from "@/layouts/AppLayout";
import { Dashboard } from "@/pages/Dashboard";
import { NewJob } from "@/pages/NewJob";
import { JobDetail } from "@/pages/JobDetail";
import { ClipViewer } from "@/pages/ClipViewer";
import { Settings } from "@/pages/Settings";
import { Login } from "@/pages/Login";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
          <p className="text-sm text-zinc-500">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="jobs/new" element={<NewJob />} />
        <Route path="jobs/:jobId" element={<JobDetail />} />
        <Route path="jobs/:jobId/clips/:rank" element={<ClipViewer />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
