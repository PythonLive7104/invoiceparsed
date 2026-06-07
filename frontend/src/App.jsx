import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth.jsx";
import Landing from "@/pages/Landing.jsx";
import { Loader2 } from "lucide-react";

// Landing is the LCP page → loaded eagerly. Everything else is code-split so it
// stays out of the homepage's initial JS bundle (Core Web Vitals).
const Login = lazy(() => import("@/pages/Login.jsx"));
const Signup = lazy(() => import("@/pages/Signup.jsx"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword.jsx"));
const ResetPassword = lazy(() => import("@/pages/ResetPassword.jsx"));
const GoogleCallback = lazy(() => import("@/pages/GoogleCallback.jsx"));
const VerifyEmail = lazy(() => import("@/pages/VerifyEmail.jsx"));
const Faq = lazy(() => import("@/pages/Faq.jsx"));
const Pricing = lazy(() => import("@/pages/Pricing.jsx"));
const About = lazy(() => import("@/pages/About.jsx"));
const BlogIndex = lazy(() => import("@/pages/BlogIndex.jsx"));
const BlogPost = lazy(() => import("@/pages/BlogPost.jsx"));
const ComparePage = lazy(() => import("@/pages/ComparePage.jsx"));
const UseCasePage = lazy(() => import("@/pages/UseCasePage.jsx"));
const DashboardShell = lazy(() => import("@/components/dashboard/DashboardShell.jsx"));
const DashboardHome = lazy(() => import("@/pages/DashboardHome.jsx"));
const History = lazy(() => import("@/pages/History.jsx"));
const ExtractionDetail = lazy(() => import("@/pages/ExtractionDetail.jsx"));
const Billing = lazy(() => import("@/pages/Billing.jsx"));
const ApiSettings = lazy(() => import("@/pages/ApiSettings.jsx"));
const Settings = lazy(() => import("@/pages/Settings.jsx"));

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
    <Suspense fallback={<FullScreenLoader />}>
        <Routes>
          <Route path="/" element={<Landing />} />

          {/* Marketing / SEO content */}
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/about" element={<About />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/blog" element={<BlogIndex />} />
          <Route path="/blog/:slug" element={<BlogPost />} />
          <Route path="/compare/:slug" element={<ComparePage />} />
          <Route path="/use-cases/:slug" element={<UseCasePage />} />

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
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    </Suspense>
  );
}
