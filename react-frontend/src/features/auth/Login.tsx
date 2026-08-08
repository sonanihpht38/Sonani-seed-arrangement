// ===================== FRONTEND: login screen =====================
// antd Form; all auth logic lives in useAuth. On success we route to the page the
// user was trying to reach, or "/" — the index route, which HomeRedirect resolves
// to the first screen the user can access (Seed Import for a production user).
// Already-authenticated users skip login.

import { useState } from "react";
import { Card, Form, Input, Button, Typography } from "antd";
import { FiUser, FiLock } from "../../components/icons";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./useAuth";
import { notify } from "../../lib/notify";
import { Logo } from "../../components/Logo";

interface LocationState {
  from?: { pathname: string };
}

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [busy, setBusy] = useState(false);

  const from = (location.state as LocationState | null)?.from?.pathname || "/";

  if (user) return <Navigate to={from} replace />;

  async function onFinish(values: { username: string; password: string }) {
    setBusy(true);
    try {
      await login(values.username, values.password);
      notify.success("Signed in");
      navigate(from, { replace: true });
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 360 }}>
        {/* The wordmark carries the product name — no separate text heading.
            `Logo` renders a display:block img, so it needs a flex row to centre. */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
          <Logo height={44} />
        </div>
        <Typography.Text type="secondary">Sign in to continue</Typography.Text>

        <Form layout="vertical" onFinish={onFinish} style={{ marginTop: 20 }} requiredMark={false}>
          <Form.Item
            name="username"
            label="Username"
            rules={[{ required: true, message: "Username is required" }]}
          >
            <Input prefix={<FiUser />} placeholder="admin" autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Password"
            rules={[{ required: true, message: "Password is required" }]}
          >
            <Input.Password prefix={<FiLock />} placeholder="••••••••" autoComplete="current-password" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={busy}>
            Sign in
          </Button>
        </Form>

        <Typography.Paragraph style={{ fontSize: 13, marginTop: 12, marginBottom: 4, textAlign: "center" }}>
          <Link to="/forgot-password">Forgot password?</Link>
        </Typography.Paragraph>
        <Typography.Paragraph style={{ fontSize: 13, marginBottom: 4, textAlign: "center" }}>
          No account? <Link to="/register">Create one</Link>
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
          Demo: <b>admin / admin123</b> (all screens) &middot; <b>manager / manager123</b> (HR &amp; Sales)
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
