import { createBrowserRouter } from "react-router";
import { PublicOnly, RequireAuth, RequireUnverified } from "./auth/guards";
import AppLayout from "./layouts/AppLayout";
import AnalyticsPage from "./pages/AnalyticsPage";
import AutomationPage from "./pages/AutomationPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomersPage from "./pages/CustomersPage";
import DashboardPage from "./pages/DashboardPage";
import InboxPage from "./pages/InboxPage";
import IntelligenceDashboardPage from "./pages/IntelligenceDashboardPage";
import IntegrationsPage from "./pages/IntegrationsPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import LandingPage from "./pages/LandingPage";
import NotFoundPage from "./pages/NotFoundPage";
import OnboardingPage from "./pages/OnboardingPage";
import ReviewPage from "./pages/ReviewPage";
import SettingsPage from "./pages/SettingsPage";
import TasksPage from "./pages/TasksPage";
import ForgotPasswordPage from "./pages/auth/ForgotPasswordPage";
import SignInPage from "./pages/auth/SignInPage";
import SignUpPage from "./pages/auth/SignUpPage";
import VerifyEmailPage from "./pages/auth/VerifyEmailPage";
import WidgetPage from "./pages/WidgetPage";

export const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  {
    element: <PublicOnly />,
    children: [
      { path: "/signin", element: <SignInPage /> },
      { path: "/signup", element: <SignUpPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
    ],
  },
  {
    element: <RequireUnverified />,
    children: [{ path: "/verify-email", element: <VerifyEmailPage /> }],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/onboarding", element: <OnboardingPage /> },
          { path: "/integrations", element: <IntegrationsPage /> },
          { path: "/inbox", element: <InboxPage /> },
          { path: "/customers", element: <CustomersPage /> },
          { path: "/customers/:customerId", element: <CustomerDetailPage /> },
          { path: "/knowledge-base", element: <KnowledgeBasePage /> },
          { path: "/review", element: <ReviewPage /> },
          { path: "/analytics", element: <AnalyticsPage /> },
          { path: "/intelligence", element: <IntelligenceDashboardPage /> },
          { path: "/automation", element: <AutomationPage /> },
          { path: "/tasks", element: <TasksPage /> },
          { path: "/settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: "/widget", element: <WidgetPage /> },
  { path: "*", element: <NotFoundPage /> },
]);
