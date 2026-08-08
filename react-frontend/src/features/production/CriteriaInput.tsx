// ===================== FRONTEND: Criteria Input =====================
// Step 3 of the plate-arrangement workflow. Collects the packing criteria the
// arrangement job (Form 5) will run with. Reads the batches chosen in Form 2 from
// sessionStorage and stores the criteria back under CRITERIA_KEY for later steps.
//
// Fixed by business rule: Mode = "Mixed" (read-only). The user sets the distance
// between seeds (mm), which is sent as `clearance`. squareTol and grid are sent as 0.

import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Form, InputNumber, Select, Input, Button, Space, Typography, Alert, Row, Col } from "antd";
import { useAuth } from "../auth/useAuth";
import type { Criteria } from "./types";
import { SELECTED_BATCHES_KEY } from "./BatchSelection";
import { FiArrowRight, FiInfo } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

/** Where the collected criteria are stashed for the Processing Option / Result steps. */
export const CRITERIA_KEY = "plateFlow.criteria";

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

interface CriteriaForm {
  shape: Criteria["shape"];
  tLo: number;
  tHi: number;
  plateD: number;
  margin: number;
  minSeed: number;
  seedDistance: number;   // distance between two seeds (mm) — sent as `clearance`
}

export function CriteriaInput() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canProceed = can("criteria_input", "save");
  const [form] = Form.useForm<CriteriaForm>();

  const selectedBatches = useMemo(() => readJson<string[]>(SELECTED_BATCHES_KEY, []), []);
  const saved = useMemo(() => readJson<Criteria | null>(CRITERIA_KEY, null), []);

  const initialValues: Partial<CriteriaForm> = saved
    ? { shape: saved.shape, tLo: saved.tLo, tHi: saved.tHi, plateD: saved.plateD, margin: saved.margin, minSeed: saved.minSeed, seedDistance: saved.clearance }
    : { shape: "all", seedDistance: 0 };

  function onFinish(values: CriteriaForm) {
    const criteria: Criteria = {
      mode: "mixed",
      shape: values.shape,
      squareTol: 0,
      tLo: values.tLo,
      tHi: values.tHi,
      plateD: values.plateD,
      margin: values.margin,
      minSeed: values.minSeed,
      clearance: values.seedDistance ?? 0,   // distance between seeds (mm)
      grid: 0,
    };
    sessionStorage.setItem(CRITERIA_KEY, JSON.stringify(criteria));
    notify.success("Criteria saved.");
    navigate("/production/processing-option");
  }

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card title="Criteria">
        <Alert
          showIcon
          icon={<FiInfo size={18} style={{ color: colors.primary }} />}
          style={{ marginBottom: 16, background: alpha(colors.primary, 0.06), border: `1px solid ${alpha(colors.primary, 0.2)}` }}
          message={
            selectedBatches.length > 0
              ? `${selectedBatches.length} batch${selectedBatches.length === 1 ? "" : "es"} selected`
              : "No batches selected — all batches will be used"
          }
          description={<Text type="secondary">Set the packing criteria for the arrangement.</Text>}
        />

        <Form<CriteriaForm> form={form} layout="vertical" initialValues={initialValues} onFinish={onFinish} requiredMark>
          <Row gutter={16}>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item label="Mode">
                <Input value="Mixed" disabled />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item name="shape" label="Shape" rules={[{ required: true, message: "Select a shape" }]}>
                <Select
                  options={[
                    { value: "all", label: "All" },
                    { value: "square", label: "Square" },
                    { value: "rectangle", label: "Rectangle" },
                  ]}
                />
              </Form.Item>
            </Col>

            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item name="tLo" label="Thickness min (mm)" rules={[{ required: true, message: "Required" }]}>
                <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="e.g. 2.0" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item
                name="tHi"
                label="Thickness max (mm)"
                dependencies={["tLo"]}
                rules={[
                  { required: true, message: "Required" },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      const lo = getFieldValue("tLo");
                      if (value == null || lo == null || value > lo) return Promise.resolve();
                      return Promise.reject(new Error("Max must be greater than min"));
                    },
                  }),
                ]}
              >
                <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="e.g. 3.5" />
              </Form.Item>
            </Col>

            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item name="plateD" label="Plate Ø (mm)" rules={[{ required: true, message: "Required" }, { type: "number", min: 0.01, message: "Must be > 0" }]}>
                <InputNumber min={0} step={1} style={{ width: "100%" }} placeholder="e.g. 100" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item
                name="margin"
                label="Margin (mm)"
                dependencies={["plateD"]}
                rules={[
                  { required: true, message: "Required" },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      const d = getFieldValue("plateD");
                      if (value == null || d == null || value < d) return Promise.resolve();
                      return Promise.reject(new Error("Margin must be less than plate Ø"));
                    },
                  }),
                ]}
              >
                <InputNumber min={0} step={0.5} style={{ width: "100%" }} placeholder="e.g. 2" />
              </Form.Item>
            </Col>

            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item name="minSeed" label="Min filler size (mm)" rules={[{ required: true, message: "Required" }]}>
                <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="e.g. 1.0" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item
                name="seedDistance"
                label="Distance between seeds (mm)"
                rules={[{ required: true, message: "Required" }, { type: "number", min: 0, message: "Must be ≥ 0" }]}
              >
                <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="e.g. 0.5" />
              </Form.Item>
            </Col>
          </Row>
        </Form>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
          <Button onClick={() => navigate("/production/batch-selection")}>← Back</Button>
          <Button
            type="primary"
            disabled={!canProceed}
            onClick={() => form.submit()}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            Save criteria &amp; continue <FiArrowRight />
          </Button>
        </div>
      </Card>
    </Space>
  );
}
