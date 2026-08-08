// ===================== FRONTEND: forgot password =====================
// Public screen: enter your email to receive a reset link. The response is
// intentionally the same whether or not the address is registered.

import { useState } from "react";
import { Card, Form, Input, Button, Typography, Result } from "antd";
import { Link } from "react-router-dom";
import { FiUser } from "../../components/icons";
import { authApi } from "./authApi";
import { notify } from "../../lib/notify";
import { Logo } from "../../components/Logo";

export function ForgotPassword() {
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function onFinish(values: { email: string }) {
    setBusy(true);
    try {
      await authApi.forgotPassword(values.email);
      setSent(true);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 380 }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
          <Logo height={44} />
        </div>

        {sent ? (
          <Result
            status="success"
            title="Check your email"
            subTitle="If that address is registered, we've sent a link to reset your password."
            extra={<Link to="/login"><Button type="primary">Back to sign in</Button></Link>}
          />
        ) : (
          <>
            <Typography.Text type="secondary">
              Enter your account email and we'll send you a reset link.
            </Typography.Text>
            <Form layout="vertical" onFinish={onFinish} style={{ marginTop: 20 }} requiredMark={false}>
              <Form.Item name="email" label="Email"
                rules={[{ required: true, type: "email", message: "A valid email is required" }]}>
                <Input prefix={<FiUser />} placeholder="you@company.com" autoComplete="email" size="large" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block size="large" loading={busy}>
                Send reset link
              </Button>
            </Form>
            <Typography.Paragraph style={{ fontSize: 13, marginTop: 16, marginBottom: 0, textAlign: "center" }}>
              Remembered it? <Link to="/login">Sign in</Link>
            </Typography.Paragraph>
          </>
        )}
      </Card>
    </div>
  );
}
