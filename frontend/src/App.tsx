import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { AppLayout } from "@/layouts/AppLayout";
import { Dashboard } from "@/pages/Dashboard";
import { NewJob } from "@/pages/NewJob";
import { JobDetail } from "@/pages/JobDetail";
import { ClipViewer } from "@/pages/ClipViewer";
import { Settings } from "@/pages/Settings";
import { SocialAccounts } from "@/pages/SocialAccounts";
import { VideoGeneratorPage } from "@/pages/VideoGenerator";
import { FacebookCallback } from "@/pages/FacebookCallback";
import { TikTokCallback } from "@/pages/TikTokCallback";
import { SocialCallback } from "@/pages/SocialCallback";
import { Login } from "@/pages/Login";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

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
    <>
      <ConfirmDialog />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/social/facebook/callback" element={<FacebookCallback />} />
        <Route path="/social/tiktok/callback" element={<TikTokCallback />} />
        <Route path="/social/instagram/callback" element={<SocialCallback />} />
        <Route path="/social/threads/callback" element={<SocialCallback />} />
        <Route path="/social/youtube/callback" element={<SocialCallback />} />
        <Route path="/social/linkedin/callback" element={<SocialCallback />} />
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
          <Route path="social" element={<SocialAccounts />} />
          <Route path="video-generator" element={<VideoGeneratorPage />} />
          <Route path="settings" element={<Navigate to="/settings/general" replace />} />
          <Route path="settings/hermes" element={<Navigate to="/settings/hermes/autopilot" replace />} />
          <Route path="settings/hermes/:subSection" element={<Settings />} />
          <Route path="settings/:section" element={<Settings />} />
          <Route path="settings/:section/:subSection" element={<Settings />} />
        </Route>
      </Routes>
    </>
  );
}
