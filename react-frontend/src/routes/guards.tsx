// Route guards. RequireAuth protects the whole authenticated area; Guarded gates
// an individual screen on a form permission (the frontend mirror of the backend's
// permission check — the server still enforces it).

import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Result, Spin } from "antd";
import { useAuth } from "../features/auth/useAuth";

export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <Outlet />;
}

export function Guarded({ form, children }: { form: string; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(form)) {
    return (
      <Result
        status="403"
        title="403"
        subTitle="You don't have permission to view this screen."
      />
    );
  }
  return <>{children}</>;
}
