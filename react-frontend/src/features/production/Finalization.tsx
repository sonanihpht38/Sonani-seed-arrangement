// ===================== FRONTEND: Finalization =====================
// Step 6. Reached from the Result screen's per-plate "Finalize this plate" button
// (stashes {jobId, arrangeId, plateNo}). Shows each plate ONE PER PAGE with BOTH
// images and BOTH reports side by side (Arrange · real seeds and Machine-Cut ·
// real + dummy), and lets the user assign a plate name chosen from the Plate Master
// pool — assigning marks the plate ISUsed, releasing returns it (IsReleased).

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, Space, Typography, Alert, Button, Row, Col, Pagination, Image, Tag, Select, Spin, Empty } from "antd";
import type { ColDef } from "ag-grid-community";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { DimRow, FinalizeContext, Job } from "./types";
import { DataGrid } from "../../components/DataGrid";
import { FiCheck, FiDownload, FiX } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

/** Handoff key from the Result screen. */
export const FINALIZE_KEY = "plateFlow.finalize";

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

const SEED_COLS: ColDef<DimRow>[] = [
  { headerName: "Type", field: "type", minWidth: 95, maxWidth: 150 },
  { headerName: "Stock", field: "stock", minWidth: 110 },
  { headerName: "W × H (mm)", field: "size", minWidth: 105, maxWidth: 130 },
  { headerName: "Thick", field: "thick", minWidth: 70, maxWidth: 90 },
  { headerName: "Shape", field: "shape", minWidth: 80, maxWidth: 110 },
];

interface PlateItem {
  plateNo: number;
  images: { label: string; url: string; fill: number }[];
  reports: { label: string; seeds: DimRow[] }[];
}

function normalize(job: Job): PlateItem[] {
  if (job.action === "compare") {
    return job.pairs.map((p) => ({
      plateNo: p.plateNo,
      images: p.panels.map((pn) => ({ label: pn.label, url: pn.imageUrl, fill: pn.fillPct })),
      reports: p.panels.map((pn) => ({ label: `${pn.label} · ${pn.seeds.length} seeds`, seeds: pn.seeds })),
    }));
  }
  const label = job.action === "arrange" ? "Arrange" : job.action === "enhanced" ? "Max Coverage" : "Machine-Cut";
  const reportLabel = job.action === "arrange" ? "Arrange · real seeds" : "Machine-Cut · real + dummy";
  return job.plates.map((p) => ({
    plateNo: p.plateNo,
    images: [{ label, url: p.imageUrl, fill: p.fillPct }],
    reports: [{ label: reportLabel, seeds: p.seeds }],
  }));
}

export function Finalization() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canFinalize = can("finalization", "save");

  const ctx = useMemo(() => readJson<FinalizeContext | null>(FINALIZE_KEY, null), []);

  const [page, setPage] = useState(1);
  const [pick, setPick] = useState<string | undefined>();

  const jobQ = useQuery({
    queryKey: ["finalize-job", ctx?.jobId],
    queryFn: () => productionApi.getJob(ctx!.jobId),
    enabled: !!ctx?.jobId,
  });
  const availQ = useQuery({ queryKey: ["available-plates"], queryFn: productionApi.availablePlates });
  const namesQ = useQuery({
    queryKey: ["plate-names", ctx?.arrangeId],
    queryFn: () => productionApi.getPlateNames(ctx!.arrangeId),
    enabled: !!ctx?.arrangeId,
  });

  const plates = useMemo(() => (jobQ.data && jobQ.data.status === "done" ? normalize(jobQ.data) : []), [jobQ.data]);
  const current = plates[page - 1];
  const names = namesQ.data?.names ?? {};
  const currentName = current ? names[String(current.plateNo)] ?? undefined : undefined;

  // Start the page on the plate the user came from.
  useEffect(() => {
    if (!plates.length || !ctx) return;
    const i = plates.findIndex((p) => p.plateNo === ctx.plateNo);
    if (i >= 0) setPage(i + 1);
  }, [plates, ctx]);

  // Sync the picker to the current plate's assigned name.
  useEffect(() => { setPick(currentName ?? undefined); }, [current, currentName]);

  // Available names from the master pool, plus the currently-assigned one (so it stays visible).
  const nameOptions = useMemo(() => {
    const set = new Set((availQ.data ?? []).map((p) => p.plateName));
    if (currentName) set.add(currentName);
    return [...set].sort().map((n) => ({ value: n, label: n }));
  }, [availQ.data, currentName]);

  const assignMut = useMutation({
    mutationFn: () => productionApi.assignPlate(ctx!.arrangeId, current!.plateNo, pick!),
    onSuccess: (r) => {
      notify.success(`Plate ${current!.plateNo} named "${r.plateName}".`);
      namesQ.refetch();
      availQ.refetch();
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Assign failed"),
  });
  const releaseMut = useMutation({
    mutationFn: () => productionApi.releasePlate(ctx!.arrangeId, current!.plateNo),
    onSuccess: () => {
      notify.success(`Plate ${current!.plateNo} name released.`);
      setPick(undefined);
      namesQ.refetch();
      availQ.refetch();
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Release failed"),
  });

  if (!ctx) {
    return (
      <Card title="Finalization">
        <Alert type="warning" showIcon message="Nothing to finalize" description="Open this from a plate's “Finalize this plate” button on the Result screen." />
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => navigate("/production/result")}>← Back to Result</Button>
        </div>
      </Card>
    );
  }

  const loading = jobQ.isLoading;

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card title="Finalization">
        <Alert
          showIcon
          style={{ background: alpha(colors.primary, 0.06), border: `1px solid ${alpha(colors.primary, 0.2)}` }}
          message={loading ? "Loading arrangement…" : `${plates.length} plate${plates.length === 1 ? "" : "s"}`}
          description={<Text type="secondary">Review each plate (both images + both reports) and assign a plate name from the master. One plate per page.</Text>}
        />
        {loading && <div style={{ padding: "16px 0" }}><Spin /></div>}
        {!loading && plates.length === 0 && <Empty style={{ marginTop: 12 }} description="No plates to finalize." />}
      </Card>

      {current && (
        <Card
          title={`Plate ${current.plateNo} of ${plates.length}`}
          extra={<Pagination simple current={page} total={plates.length} pageSize={1} onChange={setPage} />}
        >
          {/* Plate-name assignment from the master pool */}
          <Space wrap style={{ marginBottom: 16 }}>
            <Text strong>Plate name:</Text>
            <Select
              showSearch
              allowClear
              style={{ width: 220 }}
              placeholder="Select from Plate Master…"
              value={pick}
              onChange={setPick}
              options={nameOptions}
              disabled={!canFinalize}
              notFoundContent={<Text type="secondary">No plates in the master — add some in Plate Master.</Text>}
            />
            <Button
              type="primary"
              icon={<FiCheck />}
              loading={assignMut.isPending}
              disabled={!pick || !canFinalize}
              onClick={() => assignMut.mutate()}
            >
              Assign
            </Button>
            <Button
              icon={<FiX />}
              loading={releaseMut.isPending}
              disabled={!currentName || !canFinalize}
              onClick={() => releaseMut.mutate()}
            >
              Release
            </Button>
            {currentName && (
              <Tag style={{ margin: 0, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>
                assigned: {currentName}
              </Tag>
            )}
          </Space>

          {/* Each stage: image + its report, paired side by side (same-size images) */}
          <Row gutter={[16, 16]}>
            {current.images.map((img, i) => {
              const rep = current.reports[i];
              return (
                <Col key={img.label} xs={24} md={current.images.length > 1 ? 12 : 24}>
                  <div style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 12 }}>
                    <div style={{ textAlign: "center", marginBottom: 8 }}>
                      <Text strong>{img.label}</Text>
                      <Tag style={{ marginLeft: 6, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>{img.fill}% filled</Tag>
                    </div>
                    <div style={{ textAlign: "center" }}>
                      <Image src={img.url} alt={`Plate ${current.plateNo} ${img.label}`} width={480} height={480} style={{ objectFit: "contain", maxWidth: "100%" }} />
                    </div>
                    <div style={{ textAlign: "center", marginTop: 6 }}>
                      <Button size="small" icon={<FiDownload />} href={img.url} target="_blank">Download</Button>
                    </div>
                    {rep && (
                      <div style={{ marginTop: 10 }}>
                        <Text strong>{rep.label} ({rep.seeds.length})</Text>
                        <div style={{ marginTop: 6 }}>
                          <DataGrid rowData={rep.seeds} columnDefs={SEED_COLS} autoHeight paginated={false} />
                        </div>
                      </div>
                    )}
                  </div>
                </Col>
              );
            })}
          </Row>

          <div style={{ marginTop: 16 }}>
            <Button onClick={() => navigate("/production/result")}>← Back to Result</Button>
          </div>
        </Card>
      )}
    </Space>
  );
}
