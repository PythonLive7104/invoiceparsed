import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth.jsx";
import Landing from "@/pages/Landing.jsx";
import Login from "@/pages/Login.jsx";
import Signup from "@/pages/Signup.jsx";
import ForgotPassword from "@/pages/ForgotPassword.jsx";
import ResetPassword from "@/pages/ResetPassword.jsx";
import GoogleCallback from "@/pages/GoogleCallback.jsx";
import VerifyEmail from "@/pages/VerifyEmail.jsx";
import DashboardShell from "@/components/dashboard/DashboardShell.jsx";
import DashboardHome from "@/pages/DashboardHome.jsx";
import History from "@/pages/History.jsx";
import ExtractionDetail from "@/pages/ExtractionDetail.jsx";
import Billing from "@/pages/Billing.jsx";
import ApiSettings from "@/pages/ApiSettings.jsx";
import { Loader2 } from "lucide-react";

function FullScreenLoader() {
  return (
    <div className="grid min-h-screen place-items-center">
      <Loader2 className="animate-spin text-brand-400" size={28} />
    </div>
  );
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullScreenLoader />;
  if (!user)
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenLoader />;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/login"
        element={
          <PublicOnly>
            <Login />
          </PublicOnly>
        }
      />
      <Route
        path="/signup"
        element={
          <PublicOnly>
            <Signup />
          </PublicOnly>
        }
      />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/auth/google" element={<GoogleCallback />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route
        path="/dashboard"
        element={
          <Protected>
            <DashboardShell />
          </Protected>
        }
      >
        <Route index element={<DashboardHome />} />
        <Route path="history" element={<History />} />
        <Route path="extractions/:id" element={<ExtractionDetail />} />
        <Route path="api" element={<ApiSettings />} />
        <Route path="billing" element={<Billing />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
