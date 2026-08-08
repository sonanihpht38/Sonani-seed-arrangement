// ===================== FRONTEND: Batch Selection =====================
// Step 2 of the plate-arrangement workflow. After seeds are imported they are
// grouped into batches; this screen lists each batch with its seed count and lets
// the user tick one or more to carry into the criteria step. The selection is kept
// in sessionStorage under SELECTED_BATCHES_KEY so the next form (Criteria) reads it.
// Viewing is gated on the batch_selection form's permission.

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, Space, Checkbox, Tag, Empty, Typography, Button, Row, Col } from "antd";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { Batch } from "./types";
import { ActionButton, RefreshButton } from "../../components/buttons";
import { FiCheck } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

/** Where the chosen batch ids are stashed for the Criteria step to pick up. */
export const SELECTED_BATCHES_KEY = "plateFlow.selectedBatches";

export function BatchSelection() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canProceed = can("batch_selection", "save");

  const [selected, setSelected] = useState<string[]>([]);

  const batchesQ = useQuery({ queryKey: ["production-batches"], queryFn: productionApi.listBatches });
  const batches: Batch[] = batchesQ.data ?? [];

  const selectedSeeds = useMemo(
    () => batches.filter((b) => selected.includes(b.batch_id)).reduce((sum, b) => sum + b.seed_count, 0),
    [batches, selected],
  );

  const selectAll = () => setSelected(batches.map((b) => b.batch_id));
  const clearAll = () => setSelected([]);

  function proceed() {
    sessionStorage.setItem(SELECTED_BATCHES_KEY, JSON.stringify(selected));
    notify.success(`${selected.length} batch${selected.length === 1 ? "" : "es"} selected.`);
    navigate("/production/criteria");
  }

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card
        title="Batch Selection"
        loading={batchesQ.isLoading}
        extra={
          <Space>
            <RefreshButton size="small" onClick={() => batchesQ.refetch()} loading={batchesQ.isFetching} />
            {batches.length > 0 && (
              <>
                <ActionButton size="small" onClick={selectAll} disabled={selected.length === batches.length}>Select all</ActionButton>
                <ActionButton size="small" onClick={clearAll} disabled={selected.length === 0}>Clear</ActionButton>
              </>
            )}
          </Space>
        }
      >
        {batches.length === 0 ? (
          <Empty description="No batches yet — import seeds first (Seed Import)." />
        ) : (
          <Checkbox.Group value={selected} onChange={(v) => setSelected(v as string[])} style={{ width: "100%" }}>
            <Row gutter={[12, 12]}>
              {batches.map((b) => {
                const checked = selected.includes(b.batch_id);
                const disabled = b.seed_count === 0;
                return (
                  <Col key={b.batch_id} xs={24} sm={12} md={8} lg={6}>
                    <div
                      style={{
                        border: `1px solid ${checked ? colors.primary : colors.border}`,
                        background: checked ? alpha(colors.primary, 0.06) : colors.surface,
                        borderRadius: 8,
                        padding: "10px 12px",
                        height: "100%",
                        opacity: disabled ? 0.55 : 1,
                        transition: "border-color .15s, background .15s",
                      }}
                    >
                      <Checkbox value={b.batch_id} disabled={disabled} style={{ width: "100%" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", flexWrap: "wrap", gap: 8, marginLeft: 4 }}>
                          <Text strong>{b.batch_no || "—"}</Text>
                          <Tag style={{ margin: 0, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>
                            {b.seed_count} seed{b.seed_count === 1 ? "" : "s"}
                          </Tag>
                          {!b.is_active && <Tag style={{ margin: 0, background: colors.danger, color: "#fff", border: "none" }}>inactive</Tag>}
                        </span>
                      </Checkbox>
                    </div>
                  </Col>
                );
              })}
            </Row>
          </Checkbox.Group>
        )}
      </Card>

      {batches.length > 0 && (
        <Card>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Text type="secondary">
              {selected.length} batch{selected.length === 1 ? "" : "es"} · {selectedSeeds} seed{selectedSeeds === 1 ? "" : "s"} selected
            </Text>
            <Button type="primary" icon={<FiCheck />} disabled={!selected.length || !canProceed} onClick={proceed}>
              Save selection &amp; continue
            </Button>
          </Space>
        </Card>
      )}
    </Space>
  );
}
