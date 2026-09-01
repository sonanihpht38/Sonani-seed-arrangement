// ===================== FRONTEND: routes =====================
// /login is public; everything else sits behind RequireAuth + the AppLayout
// shell. The authenticated route table is DATA (routes/registry.ts) — the same
// way the sidebar menu already is — so adding a module means adding its
// routes.ts to the registry, not editing this file.

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";
import { Button, Result, Spin } from "antd";

import { Login } from "./features/auth/Login";
import { Register } from "./features/auth/Register";
import { ForgotPassword } from "./features/auth/ForgotPassword";
import { ResetPassword } from "./features/auth/ResetPassword";
import { AppLayout } from "./layout/AppLayout";
import { RequireAuth, Guarded } from "./routes/guards";
import { ROUTES } from "./routes/registry";
import { useAuth } from "./features/auth/useAuth";
import { accessApi } from "./features/access/accessApi";

// Land each user on the first sidebar item their permissions allow — driven by
// the same catalogue the menu renders, so the landing screen and the first
// visible menu entry always agree (no hardcoded order to maintain).
function HomeRedirect() {
  const { can } = useAuth();
  const catalogueQ = useQuery({ queryKey: ["catalogue"], queryFn: accessApi.catalogue });
  if (catalogueQ.isPending) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: 240 }}>
        <Spin />
      </div>
    );
  }
  // A FAILED catalogue call is not the same as an empty one. Both used to land
  // on "No access", so a user whose request was throttled or whose network
  // blipped signed in successfully and was then told their account had no
  // screens — which sent people looking for a permissions problem that did not
  // exist. Say what actually happened, and let them retry.
  if (catalogueQ.isError) {
    const err = catalogueQ.error as { status?: number; message?: string };
    const throttled = err?.status === 429;
    return (
      <Result
        status={throttled ? "warning" : "error"}
        title={throttled ? "Too many requests" : "Could not load your screens"}
        subTitle={
          throttled
            ? `${err.message ?? "The API is rate-limiting this account."} Your sign-in worked — this is a temporary limit, not a permissions problem.`
            : (err?.message ?? "The server did not return your form list.")
        }
        extra={
          <Button type="primary" onClick={() => catalogueQ.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }
  const target = (catalogueQ.data ?? [])
    .flatMap((group) => group.forms)
    .find((f) => f.is_active && f.route && can(f.code))?.route;
  if (!target) {
    return <Result status="403" title="No access" subTitle="Your account has no screens assigned yet." />;
  }
  return <Navigate to={target} replace />;
}

const Loading = () => (
  <div style={{ display: "grid", placeItems: "center", minHeight: 240 }}>
    <Spin />
  </div>
);

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<HomeRedirect />} />
          {ROUTES.map(({ form, path, Component }) => (
            <Route
              key={path}
              path={path}
              element={
                <Guarded form={form}>
                  <Suspense fallback={<Loading />}>
                    <Component />
                  </Suspense>
                </Guarded>
              }
            />
          ))}
          <Route
            path="*"
            element={<Result status="404" title="404" subTitle="Page not found." />}
          />
        </Route>
      </Route>
    </Routes>
  );
}
