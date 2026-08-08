// ===================== FRONTEND: reset password =====================
// Public screen reached from the emailed link (/reset-password?uid=…&token=…).
// Sets a new password after re-validating the token server-side.

import { useState } from "react";
import { Card, Form, Input, Button, Typography, Result } from "antd";
import { Link, useSearchParams } from "react-router-dom";
import { FiLock } from "../../components/icons";
import { authApi } from "./authApi";
import { notify } from "../../lib/notify";
import { Logo } from "../../components/Logo";

export function ResetPassword() {
  const [params] = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const missingLink = !uid || !token;

  async function onFinish(values: { password: string; confirm: string }) {
    if (values.password !== values.confirm) {
      notify.error("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await authApi.resetPassword(uid, token, values.password);
      setDone(true);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Reset failed");
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

        {done ? (
          <Result
            status="success"
            title="Password updated"
            subTitle="You can now sign in with your new password."
            extra={<Link to="/login"><Button type="primary">Sign in</Button></Link>}
          />
        ) : missingLink ? (
          <Result
            status="warning"
            title="Invalid reset link"
            subTitle="This link is missing information. Please request a new one."
            extra={<Link to="/forgot-password"><Button type="primary">Request new link</Button></Link>}
          />
        ) : (
          <>
            <Typography.Text type="secondary">Choose a new password.</Typography.Text>
            <Form layout="vertical" onFinish={onFinish} style={{ marginTop: 20 }} requiredMark={false}>
              <Form.Item name="password" label="New password"
                rules={[{ required: true, min: 8, message: "At least 8 characters" }]}>
                <Input.Password prefix={<FiLock />} placeholder="••••••••" autoComplete="new-password" size="large" />
              </Form.Item>
              <Form.Item name="confirm" label="Confirm password"
                dependencies={["password"]}
                rules={[{ required: true, message: "Please confirm your password" }]}>
                <Input.Password prefix={<FiLock />} placeholder="••••••••" autoComplete="new-password" size="large" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block size="large" loading={busy}>
                Reset password
              </Button>
            </Form>
            <Typography.Paragraph style={{ fontSize: 13, marginTop: 16, marginBottom: 0, textAlign: "center" }}>
              <Link to="/login">Back to sign in</Link>
            </Typography.Paragraph>
          </>
        )}
      </Card>
    </div>
  );
}
