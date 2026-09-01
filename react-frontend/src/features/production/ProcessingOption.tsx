// ===================== FRONTEND: Processing Option =====================
// Step 4 of the plate-arrangement workflow. The user picks ONE processing option
// (Arrange / Machine-Cut Fill / Compare / Max Coverage). It maps to the arrangement
// job's `action`. Reads the batches + criteria from the previous steps (as a summary)
// and stores the chosen action under ACTION_KEY for the Result step (Form 5).

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Row, Col, Button, Space, Typography, Alert, Checkbox } from "antd";
import { useAuth } from "../auth/useAuth";
import type { Action, Criteria } from "./types";
import { SELECTED_BATCHES_KEY } from "./BatchSelection";
import { CRITERIA_KEY, describeWidthBand } from "./CriteriaInput";
import { FiGrid, FiPackage, FiCopy, FiZap, FiArrowRight, FiCheck, FiInfo } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text, Title } = Typography;

/** Where the chosen processing option is stashed for the Result step. */
export const ACTION_KEY = "plateFlow.action";
/** For Compare: which methods (2 or 3) the user wants to compare. */
export const COMPARE_METHODS_KEY = "plateFlow.compareMethods";

export type CompareMethod = "arrange" | "machinefill" | "enhanced";

/** Options hidden from the UI. The engine still supports them — drop the entry to bring one back. */
const HIDDEN: ReadonlySet<string> = new Set(["machinefill"]);

const ALL_COMPARE_CHOICES: { value: CompareMethod; label: string }[] = [
  { value: "arrange", label: "Arrange" },
  { value: "machinefill", label: "Machine-Cut Fill" },
  { value: "enhanced", label: "Max Coverage" },
];
const COMPARE_CHOICES = ALL_COMPARE_CHOICES.filter((c) => !HIDDEN.has(c.value));

/** Compare methods ticked by default (visible ones only). */
const DEFAULT_METHODS = COMPARE_CHOICES.map((c) => c.value);

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

const ALL_OPTIONS: { value: Action; title: string; desc: string; Icon: typeof FiGrid }[] = [
  { value: "arrange", title: "Arrange", desc: "Place the real seeds onto plates.", Icon: FiGrid },
  { value: "machinefill", title: "Machine-Cut Fill", desc: "Arrange real seeds, then fill the gaps with dummy fillers.", Icon: FiPackage },
  { value: "enhanced", title: "Max Coverage", desc: "Grow the arranged seeds to the plate edge and trim any overhanging seeds with a straight cut — highest coverage, all real seeds.", Icon: FiZap },
  { value: "compare", title: "Compare", desc: "Run the methods and view them side by side to compare coverage.", Icon: FiCopy },
];
const OPTIONS = ALL_OPTIONS.filter((o) => !HIDDEN.has(o.value));

/** Card width so the visible options fill the row evenly (4 → 6, 3 → 8, 2 → 12). */
const CARD_LG = Math.floor(24 / Math.max(1, OPTIONS.length));

export function ProcessingOption() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canProceed = can("processing_option", "save");

  const selectedBatches = useMemo(() => readJson<string[]>(SELECTED_BATCHES_KEY, []), []);
  const criteria = useMemo(() => readJson<Criteria | null>(CRITERIA_KEY, null), []);
  const saved = useMemo(() => readJson<Action | null>(ACTION_KEY, null), []);
  const savedMethods = useMemo(
    () => readJson<CompareMethod[]>(COMPARE_METHODS_KEY, DEFAULT_METHODS).filter((m) => !HIDDEN.has(m)),
    [],
  );

  const [action, setAction] = useState<Action | null>(saved);
  const [methods, setMethods] = useState<CompareMethod[]>(savedMethods);

  const hasCriteria = criteria !== null;
  const tooFewMethods = action === "compare" && methods.length < 2;

  function proceed() {
    if (!action || tooFewMethods) return;
    sessionStorage.setItem(ACTION_KEY, JSON.stringify(action));
    if (action === "compare") {
      // Keep canonical order so the panels always read arrange → machine → max-coverage.
      const ordered = COMPARE_CHOICES.map((c) => c.value).filter((m) => methods.includes(m));
      sessionStorage.setItem(COMPARE_METHODS_KEY, JSON.stringify(ordered));
    }
    notify.success(`"${OPTIONS.find((o) => o.value === action)?.title}" selected.`);
    navigate("/production/result");
  }

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card title="Processing Option">
        <Alert
          showIcon
          icon={<FiInfo size={18} style={{ color: hasCriteria ? colors.primary : colors.danger }} />}
          type={hasCriteria ? "info" : "warning"}
          style={{
            marginBottom: 16,
            background: alpha(hasCriteria ? colors.primary : colors.danger, 0.06),
            border: `1px solid ${alpha(hasCriteria ? colors.primary : colors.danger, 0.2)}`,
          }}
          message={
            hasCriteria
              ? `${selectedBatches.length || "All"} batch${selectedBatches.length === 1 ? "" : "es"} · shape ${criteria!.shape} · thickness ${criteria!.tLo}–${criteria!.tHi}mm${
                  describeWidthBand(criteria) ? ` · seed width ${describeWidthBand(criteria)}` : ""
                } · plate Ø ${criteria!.plateD}mm`
              : "No criteria set — go back and set the criteria first."
          }
          description={<Text type="secondary">Choose how to process the selected seeds.</Text>}
        />

        <Row gutter={[16, 16]}>
          {OPTIONS.map((o) => {
            const selected = action === o.value;
            return (
              <Col key={o.value} xs={24} md={12} lg={CARD_LG}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setAction(o.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setAction(o.value); }}
                  style={{
                    border: `1px solid ${selected ? colors.primary : colors.border}`,
                    background: selected ? alpha(colors.primary, 0.06) : colors.surface,
                    borderRadius: 10,
                    padding: 16,
                    height: "100%",
                    cursor: "pointer",
                    transition: "border-color .15s, background .15s",
                    display: "flex",
                    gap: 14,
                    alignItems: "flex-start",
                  }}
                >
                  <div
                    style={{
                      flexShrink: 0,
                      width: 44,
                      height: 44,
                      borderRadius: 10,
                      background: alpha(colors.primary, selected ? 0.16 : 0.09),
                      display: "grid",
                      placeItems: "center",
                    }}
                  >
                    <o.Icon size={22} style={{ color: colors.primary }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Title level={5} style={{ margin: 0 }}>{o.title}</Title>
                      {selected && <FiCheck size={16} style={{ color: colors.primary, marginLeft: "auto" }} />}
                    </div>
                    <Text type="secondary">{o.desc}</Text>
                  </div>
                </div>
              </Col>
            );
          })}
        </Row>

        {action === "compare" && (
          <div
            style={{
              marginTop: 16,
              padding: 16,
              borderRadius: 10,
              border: `1px solid ${alpha(colors.primary, 0.2)}`,
              background: alpha(colors.primary, 0.04),
            }}
          >
            <Text strong>Which methods do you want to compare?</Text>
            <div style={{ marginTop: 4, marginBottom: 10 }}>
              <Text type="secondary">Tick at least two methods — the results page will show them side by side for comparison.</Text>
            </div>
            <Checkbox.Group
              value={methods}
              onChange={(v) => setMethods(v as CompareMethod[])}
              options={COMPARE_CHOICES}
            />
            {tooFewMethods && (
              <div style={{ marginTop: 8 }}>
                <Text type="danger">Select at least two methods to compare.</Text>
              </div>
            )}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
          <Button onClick={() => navigate("/production/criteria")}>← Back</Button>
          <Button
            type="primary"
            disabled={!action || !canProceed || tooFewMethods}
            onClick={proceed}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            Continue <FiArrowRight />
          </Button>
        </div>
      </Card>
    </Space>
  );
}
