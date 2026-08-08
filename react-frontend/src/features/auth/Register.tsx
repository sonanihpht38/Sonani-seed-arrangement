// ===================== FRONTEND: registration =====================
// Public self-registration. Creates an inactive account; the user is told an
// admin must approve it before they can sign in.

import { useState } from "react";
import { Card, Form, Input, Button, Typography, Result } from "antd";
import { FiUser, FiLock } from "../../components/icons";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "./useAuth";
import { authApi } from "./authApi";
import { notify } from "../../lib/notify";

export function Register() {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onFinish(values: {
    username: string; email: string; password: string;
    first_name?: string; last_name?: string;
  }) {
    setBusy(true);
    try {
      const res = await authApi.register(values);
      notify.success(res.detail);
      setDone(true);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 400 }}>
        {done ? (
          <Result
            status="success"
            title="Account created"
            subTitle="Your account is ready. You can sign in now."
            extra={<Link to="/login"><Button type="primary">Sign in</Button></Link>}
          />
        ) : (
          <>
            <Typography.Title level={3} style={{ marginBottom: 4 }}>Create account</Typography.Title>
            <Typography.Text type="secondary">Register for Sonani Seed Arrangement</Typography.Text>

            <Form layout="vertical" onFinish={onFinish} style={{ marginTop: 20 }} requiredMark={false}>
              <Form.Item name="username" label="Username" rules={[{ required: true, message: "Username is required" }]}>
                <Input prefix={<FiUser />} autoComplete="username" size="large" />
              </Form.Item>
              <Form.Item name="email" label="Email" rules={[{ required: true, type: "email", message: "A valid email is required" }]}>
                <Input autoComplete="email" size="large" />
              </Form.Item>
              <div style={{ display: "flex", gap: 12 }}>
                <Form.Item name="first_name" label="First name" style={{ flex: 1 }}>
                  <Input size="large" />
                </Form.Item>
                <Form.Item name="last_name" label="Last name" style={{ flex: 1 }}>
                  <Input size="large" />
                </Form.Item>
              </div>
              <Form.Item name="password" label="Password" rules={[{ required: true, min: 8, message: "At least 8 characters" }]}>
                <Input.Password prefix={<FiLock />} autoComplete="new-password" size="large" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block size="large" loading={busy}>
                Create account
              </Button>
            </Form>

            <Typography.Paragraph style={{ fontSize: 13, marginTop: 16, marginBottom: 0, textAlign: "center" }}>
              Already have an account? <Link to="/login">Sign in</Link>
            </Typography.Paragraph>
          </>
        )}
      </Card>
    </div>
  );
}
