// ===================== FRONTEND: Criteria Input =====================
// Step 3 of the plate-arrangement workflow. Collects the packing criteria the
// arrangement job (Form 5) will run with. Reads the batches chosen in Form 2 from
// sessionStorage and stores the criteria back under CRITERIA_KEY for later steps.
//
// Fixed by business rule: Mode = "Mixed" (read-only). The user sets the distance
// between seeds (mm), which is sent as `clearance`. grid is sent as 0.
//
// `squareTol` decides where the line between "square" and "rectangle" falls, and
// it ONLY matters when Shape is Square or Rectangle — with Shape = All both
// classes are accepted and the value changes nothing. It used to be hardcoded to
// 0, which means "square" required L to equal W exactly; no stone measured to two
// decimals ever does, so Shape = Square matched nothing at all and Shape =
// Rectangle quietly matched everything, making it identical to All.

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

/**
 * Human-readable seed-width band, or null when the user bounded neither end.
 * Shared by every screen that summarises the criteria, so the band is described
 * the same way everywhere ("8–12 mm", "≤ 12 mm", "≥ 8 mm").
 */
export function describeWidthBand(c: Pick<Criteria, "wLo" | "wHi"> | null): string | null {
  if (!c) return null;
  const lo = c.wLo ?? null;
  const hi = c.wHi ?? null;
  if (lo == null && hi == null) return null;
  if (lo != null && hi != null) return `${lo}–${hi} mm`;
  return lo != null ? `≥ ${lo} mm` : `≤ ${hi} mm`;
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

/** Where "square" ends and "rectangle" begins, as a fraction of the longer side.
 *  0.05 is the packing engine's own long-standing default. */
export const SQUARE_TOL_DEFAULT = 0.05;

interface CriteriaForm {
  shape: Criteria["shape"];
  /** Only consulted when shape is Square or Rectangle — see the note at the top. */
  squareTol: number;
  tLo: number;
  tHi: number;
  /** Seed width band (mm) — OPTIONAL at both ends. Blank = no bound. */
  wLo?: number | null;
  wHi?: number | null;
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
    ? { shape: saved.shape, squareTol: saved.squareTol || SQUARE_TOL_DEFAULT, tLo: saved.tLo, tHi: saved.tHi, wLo: saved.wLo, wHi: saved.wHi, plateD: saved.plateD, margin: saved.margin, minSeed: saved.minSeed, seedDistance: saved.clearance }
    : { shape: "all", squareTol: SQUARE_TOL_DEFAULT, seedDistance: 0 };

  function onFinish(values: CriteriaForm) {
    const criteria: Criteria = {
      mode: "mixed",
      shape: values.shape,
      // Only consulted when shape is Square or Rectangle. With shape "all" both
      // classes are accepted, so this value cannot change which seeds are
      // arranged — existing All runs are unaffected by it entirely.
      squareTol: values.squareTol ?? SQUARE_TOL_DEFAULT,
      tLo: values.tLo,
      tHi: values.tHi,
      // Seed-width band. An emptied InputNumber gives null; send null rather
      // than 0 so "no minimum" stays distinct from "minimum of 0 mm" all the
      // way through to the stored TRN_SeedArrange row.
      wLo: values.wLo ?? null,
      wHi: values.wHi ?? null,
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
            {/* Shown only when it does something. With Shape = All both classes
                are accepted, so the threshold cannot affect the arrangement —
                displaying it there would invite someone to tune a dial that is
                not connected to anything. */}
            <Form.Item noStyle shouldUpdate={(a, b) => a.shape !== b.shape}>
              {({ getFieldValue }) =>
                getFieldValue("shape") === "all" ? null : (
                  <Col xs={24} sm={12} md={8} lg={6}>
                    <Form.Item
                      name="squareTol"
                      label="Square tolerance"
                      tooltip="How close to equal a seed's two sides must be to count as SQUARE, as a fraction of the longer side. 0.05 means within 5%. At 0 a seed must be exactly square, which no measured stone ever is — so Square would match nothing and Rectangle would match everything."
                      rules={[
                        { required: true, message: "Required" },
                        { type: "number", min: 0, max: 1, message: "Between 0 and 1" },
                      ]}
                    >
                      <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} placeholder="e.g. 0.05" />
                    </Form.Item>
                  </Col>
                )
              }
            </Form.Item>

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

            {/* Seed-width band — REQUIRED, both ends. It is a manufacturing
                constraint rather than a convenience: an unbounded pool mixes
                2 mm stones with 14 mm ones and produces a plate that scores
                well on coverage but that the floor will not build. Stating the
                range is also the single biggest lever on generation time. */}
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item
                name="wLo"
                label="Seed width min (mm)"
                tooltip="Seed width is the SHORTER of a seed's two sides, so it does not depend on which way round the seed was measured. Seeds narrower than this are left out."
                dependencies={["wHi"]}
                rules={[
                  { required: true, message: "Required" },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      const hi = getFieldValue("wHi");
                      if (value == null || hi == null || value <= hi) return Promise.resolve();
                      return Promise.reject(new Error("Min must be ≤ max"));
                    },
                  }),
                ]}
              >
                <InputNumber min={0} step={0.5} style={{ width: "100%" }} placeholder="e.g. 8" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Form.Item
                name="wHi"
                label="Seed width max (mm)"
                tooltip="Seeds wider than this are left out of the arrangement. Keep the band reasonably tight — a narrow band packs faster and gives a more uniform, more buildable plate."
                dependencies={["wLo"]}
                rules={[
                  { required: true, message: "Required" },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      const lo = getFieldValue("wLo");
                      if (value == null || lo == null || value >= lo) return Promise.resolve();
                      return Promise.reject(new Error("Max must be ≥ min"));
                    },
                  }),
                ]}
              >
                <InputNumber min={0} step={0.5} style={{ width: "100%" }} placeholder="e.g. 12" />
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
