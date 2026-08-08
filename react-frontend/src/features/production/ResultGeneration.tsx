// ===================== FRONTEND: Result Generation =====================
// Step 5 of the plate-arrangement workflow. Reads the batches + criteria + chosen
// action from the previous steps, starts an arrangement job (POST /production/jobs),
// polls it to completion, then shows the plates ONE PER PAGE (pagination), each with
// its image(s), seed detail table, and per-plate action buttons.

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, Space, Typography, Alert, Progress, Button, Row, Col, Pagination, Empty, Tag, Image, Spin, Checkbox } from "antd";
import type { ColDef } from "ag-grid-community";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { Action, Criteria, DimRow, Job } from "./types";
import { SELECTED_BATCHES_KEY } from "./BatchSelection";
import { CRITERIA_KEY } from "./CriteriaInput";
import { ACTION_KEY, COMPARE_METHODS_KEY } from "./ProcessingOption";
import { DataGrid } from "../../components/DataGrid";
import { FiCheck, FiDownload, FiRefreshCw } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

const ACTION_LABEL: Record<Action, string> = {
  arrange: "Arrange",
  machinefill: "Machine-Cut Fill",
  compare: "Compare",
  enhanced: "Max Coverage",
};

interface PlateItem {
  plateNo: number;
  images: { label: string; url: string; fill: number; method?: string }[];
  reports: { label: string; seeds: DimRow[] }[];
  exportUrl?: string;
}

function normalize(job: Job): PlateItem[] {
  if (job.action === "compare") {
    return job.pairs.map((p) => ({
      plateNo: p.plateNo,
      // One image + one full seed table per selected method (2 or 3), side by side.
      images: p.panels.map((pn) => ({ label: pn.label, url: pn.imageUrl, fill: pn.fillPct, method: pn.method })),
      reports: p.panels.map((pn) => ({
        label: `${pn.label} · ${pn.seeds.length} seeds`,
        seeds: pn.seeds,
      })),
      exportUrl: p.exportUrl,
    }));
  }
  const label = job.action === "arrange" ? "Arrange" : job.action === "enhanced" ? "Max Coverage" : "Machine-Cut";
  const reportLabel = job.action === "arrange" ? "Arrange · real seeds" : job.action === "enhanced" ? "Max Coverage · real seeds" : "Machine-Cut · real + dummy";
  return job.plates.map((p) => ({
    plateNo: p.plateNo,
    images: [{ label, url: p.imageUrl, fill: p.fillPct }],
    reports: [{ label: reportLabel, seeds: p.seeds }],
    exportUrl: p.exportUrl,
  }));
}

const SEED_COLS: ColDef<DimRow>[] = [
  { headerName: "Type", field: "type", minWidth: 95, maxWidth: 160 },
  { headerName: "Stock", field: "stock", minWidth: 110 },
  { headerName: "W × H (mm)", field: "size", minWidth: 105, maxWidth: 130 },
  { headerName: "Thick", field: "thick", minWidth: 70, maxWidth: 90 },
  { headerName: "Shape", field: "shape", minWidth: 80, maxWidth: 110 },
  // "Cut off" is gone: seeds arrive already cut, the engine never cuts one, so
  // the column showed "—" on every row of every plate.
  { headerName: "Center", field: "center", minWidth: 100, maxWidth: 130 },
];

// Force a real "Save file" instead of navigating/opening in a new tab. The image is
// served cross-origin (backend :8000) so the plain <a download> attribute is ignored;
// fetch it as a blob and download that. Falls back to opening the URL on any error.
async function saveUrlAsFile(url: string, filename: string) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(String(res.status));
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objUrl);
  } catch {
    window.open(url, "_blank");
  }
}

export function ResultGeneration() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canRun = can("result_generation", "save");

  const action = useMemo(() => readJson<Action | null>(ACTION_KEY, null), []);
  const criteria = useMemo(() => readJson<Criteria | null>(CRITERIA_KEY, null), []);
  const batches = useMemo(() => readJson<string[]>(SELECTED_BATCHES_KEY, []), []);
  const compareMethods = useMemo(
    () => readJson<string[]>(COMPARE_METHODS_KEY, ["arrange", "enhanced"]),
    [],
  );

  const [jobId, setJobId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const startedRef = useRef(false);

  const jobMut = useMutation({
    mutationFn: () =>
      productionApi.createJob(action!, {
        ...(criteria as Criteria),
        batches,
        ...(action === "compare" ? { methods: compareMethods } : {}),
      }),
    onSuccess: (r) => { setJobId(r.id); setPage(1); },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Failed to start the job"),
  });

  const jobQ = useQuery({
    queryKey: ["prod-job", jobId],
    queryFn: () => productionApi.getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "done" || s === "failed" ? false : 1000;
    },
    refetchIntervalInBackground: true, // keep polling even when the tab isn't focused
  });

  // Auto-run once when we arrive with a valid action + criteria.
  useEffect(() => {
    if (action && criteria && canRun && !startedRef.current) {
      startedRef.current = true;
      jobMut.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const job = jobQ.data;
  const plates = useMemo(() => (job && job.status === "done" ? normalize(job) : []), [job]);
  const current = plates[page - 1];

  // Compare-only: which methods to actually show side by side. The user can filter a
  // 3-way run down to any pair (or one) on screen — no re-run. null = show all generated.
  const isCompare = action === "compare";
  const compareOptions = useMemo(
    () =>
      isCompare && plates[0]
        ? plates[0].images.filter((im) => im.method).map((im) => ({ value: im.method!, label: im.label }))
        : [],
    [isCompare, plates],
  );
  const [visibleMethods, setVisibleMethods] = useState<string[] | null>(null);
  const optKey = compareOptions.map((o) => o.value).join(",");
  // Reset the filter to "show all" whenever the available methods change (a new/re-run job).
  useEffect(() => { setVisibleMethods(null); }, [optKey]);
  const effVisible = visibleMethods ?? compareOptions.map((o) => o.value);
  const panels = current
    ? current.images
        .map((img, i) => ({ img, rep: current.reports[i] }))
        .filter(({ img }) => !isCompare || !img.method || effVisible.includes(img.method))
    : [];
  const panelSpan = panels.length === 1 ? 24 : panels.length === 2 ? 12 : 8;
  const panelBig = panels.length === 1;

  function rerun() {
    setJobId(null);
    jobMut.mutate();
  }

  // ---- guards ----
  if (!action || !criteria) {
    return (
      <Card title="Result">
        <Alert
          type="warning"
          showIcon
          message="Missing steps"
          description="Choose batches, set the criteria, and pick a processing option first."
        />
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => navigate("/production/processing-option")}>← Back to Processing Option</Button>
        </div>
      </Card>
    );
  }

  const failed = job?.status === "failed";
  const finished = job?.status === "done" || failed;
  const noSeeds = job?.status === "done" && (job.seedsMatched === 0 || plates.length === 0);
  // Actively polling a queued/running job (NOT once it's done/failed).
  const polling = !!job && (job.status === "queued" || job.status === "running");
  // "running" = starting or polling — but ALWAYS false once the job has finished,
  // regardless of a lingering mutation-pending flag.
  const running = !finished && (jobMut.isPending || (!!jobId && !job) || polling);

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card
        title={`Result — ${ACTION_LABEL[action]}`}
        extra={
          <Space>
            {job?.status === "done" && !noSeeds && plates.length > 0 && (
              <Button
                size="small"
                icon={<FiDownload />}
                onClick={() => {
                  sessionStorage.setItem("plateFlow.download", JSON.stringify({ jobId: job.id }));
                  navigate("/production/download");
                }}
              >
                Download plates
              </Button>
            )}
            <Button size="small" icon={<FiRefreshCw />} onClick={rerun} disabled={running || !canRun}>
              Re-run
            </Button>
          </Space>
        }
      >
        <Alert
          showIcon
          style={{ marginBottom: 16, background: alpha(colors.primary, 0.06), border: `1px solid ${alpha(colors.primary, 0.2)}` }}
          message={`${batches.length || "All"} batch${batches.length === 1 ? "" : "es"} · shape ${criteria.shape} · thickness ${criteria.tLo}–${criteria.tHi}mm · plate Ø ${criteria.plateD}mm`}
          description={
            running ? (
              <Text type="secondary">Generating the plate arrangement…</Text>
            ) : job?.status === "done" && !noSeeds ? (
              <Space size="large" wrap>
                <Text>Plates: <b>{plates.length}</b></Text>
                {(action === "arrange" || (action === "compare" && compareMethods.includes("arrange"))) && <Text>Arrange avg: <b>{job.arrangeAvg}%</b></Text>}
                {(action === "machinefill" || (action === "compare" && compareMethods.includes("machinefill"))) && <Text>Machine-Cut avg: <b>{job.machineAvg}%</b></Text>}
                {(action === "enhanced" || (action === "compare" && compareMethods.includes("enhanced"))) && <Text>Max Coverage avg: <b>{job.enhancedAvg}%</b></Text>}
              </Space>
            ) : (
              <Text type="secondary">Choose how to process the selected seeds.</Text>
            )
          }
        />

        {running && (
          <div style={{ padding: "4px 0" }}>
            <Progress
              percent={job?.progress ?? 5}
              status="active"
              strokeColor={{ from: colors.primaryLight, to: colors.primary }}
              trailColor={alpha(colors.primary, 0.1)}
            />
            <Space size={8} style={{ marginTop: 4 }}>
              <Spin size="small" />
              <Text type="secondary">{polling && job?.status === "running" ? "Packing seeds onto plates…" : "Starting the engine…"}</Text>
            </Space>
          </div>
        )}

        {failed && (
          <Alert type="error" showIcon message="Job failed" description={<pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{job?.error}</pre>} />
        )}

        {noSeeds && (
          <Empty description="No seeds matched the selected criteria. Widen the thickness range, change the shape, or pick different batches." />
        )}
      </Card>

      {current && (
        <Card
          title={`Plate ${current.plateNo} of ${plates.length}`}
          extra={
            <Pagination
              simple
              current={page}
              total={plates.length}
              pageSize={1}
              onChange={setPage}
            />
          }
        >
          {isCompare && compareOptions.length > 1 && (
            <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 8, background: alpha(colors.primary, 0.05), border: `1px solid ${alpha(colors.primary, 0.18)}`, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <Text strong>Compare:</Text>
              <Checkbox.Group
                options={compareOptions}
                value={effVisible}
                onChange={(v) => setVisibleMethods((v as string[]).length ? (v as string[]) : null)}
              />
              <Text type="secondary">Tick the methods to view side by side (pick any 2 to compare a pair).</Text>
            </div>
          )}
          {panels.length === 0 ? (
            <Empty description="No methods selected — tick at least one above." />
          ) : (
            <Row gutter={[16, 16]}>
              {panels.map(({ img, rep }) => (
                <Col key={img.label} xs={24} md={panelSpan}>
                  <div style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 12 }}>
                    <div style={{ textAlign: "center", marginBottom: 8 }}>
                      <Text strong>{img.label}</Text>
                      <Tag style={{ marginLeft: 6, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>{img.fill}% filled</Tag>
                    </div>
                    <div style={{ textAlign: "center" }}>
                      {/* Plate images are wide (plate + seed list). One panel → big box; two/three → narrower box. */}
                      <Image src={img.url} alt={`Plate ${current.plateNo} ${img.label}`} width={panelBig ? 860 : 470} height={panelBig ? 570 : 312} style={{ objectFit: "contain", maxWidth: "100%" }} />
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
              ))}
            </Row>
          )}

          {/* Per-plate action buttons */}
          <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button
              type="primary"
              icon={<FiCheck />}
              onClick={() => {
                if (!job?.arrangeId) { notify.warning("No saved arrangement to finalize."); return; }
                sessionStorage.setItem("plateFlow.finalize", JSON.stringify({ jobId: job.id, arrangeId: job.arrangeId, plateNo: current.plateNo }));
                navigate("/production/finalize");
              }}
            >
              Finalize this plate
            </Button>
            {current.exportUrl && (
              <Button
                icon={<FiDownload />}
                onClick={() =>
                  saveUrlAsFile(current.exportUrl!, `plate-${current.plateNo}.xlsx`)
                }
              >
                Download Excel
              </Button>
            )}
            {current.images.map((img) => (
              <Button
                key={img.label}
                icon={<FiDownload />}
                onClick={() =>
                  saveUrlAsFile(img.url, `${img.label}-plate-${current.plateNo}.png`)
                }
              >
                {img.label} image
              </Button>
            ))}
          </div>
        </Card>
      )}
    </Space>
  );
}
