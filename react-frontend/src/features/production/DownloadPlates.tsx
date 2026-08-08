// ===================== FRONTEND: Download =====================
// Step 7 of the plate-arrangement workflow. Reached from the Result / Finalize
// screens (which stash {jobId} under DOWNLOAD_KEY). Lists the arrangement's plates
// with checkboxes; the user picks plates + what to include (data / images / both)
// and downloads a .zip. Data = per-plate Excel (Max Coverage); images = the Arrange /
// Machine-Cut / Max Coverage / Finalized PNGs.

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, Space, Typography, Alert, Button, Checkbox, Radio, Tag, Empty, Spin } from "antd";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import type { Job } from "./types";
import { ActionButton } from "../../components/buttons";
import { FiDownload } from "../../components/icons";
import { notify } from "../../lib/notify";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

/** Handoff key from the Result / Finalize screens. */
export const DOWNLOAD_KEY = "plateFlow.download";

type Include = "both" | "data" | "images";

function readJson<T>(key: string, fallback: T): T {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function DownloadPlates() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const canDownload = can("download", "view");

  const ctx = useMemo(() => readJson<{ jobId: string } | null>(DOWNLOAD_KEY, null), []);

  const [selected, setSelected] = useState<number[]>([]);
  const [include, setInclude] = useState<Include>("both");

  const jobQ = useQuery({
    queryKey: ["prod-download-job", ctx?.jobId],
    queryFn: () => productionApi.getJob(ctx!.jobId),
    enabled: !!ctx?.jobId,
  });
  const namesQ = useQuery({
    queryKey: ["prod-download-names", jobQ.data?.arrangeId],
    queryFn: () => productionApi.getPlateNames(jobQ.data!.arrangeId!),
    enabled: !!jobQ.data?.arrangeId,
  });

  const job: Job | undefined = jobQ.data;
  const plateNos = useMemo(() => {
    if (!job) return [];
    const list = job.action === "compare" ? job.pairs : job.plates;
    return list.map((p) => p.plateNo);
  }, [job]);
  const names = namesQ.data?.names ?? {};
  const hasExcel = job?.action === "compare" || job?.action === "enhanced";

  // Select all plates by default once loaded.
  useEffect(() => {
    if (plateNos.length) setSelected(plateNos);
  }, [plateNos]);

  const downloadMut = useMutation({
    mutationFn: () => productionApi.downloadPlates(ctx!.jobId, selected, include),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `plates_${ctx!.jobId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notify.success(`Downloaded ${selected.length} plate${selected.length === 1 ? "" : "s"}.`);
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Download failed"),
  });

  if (!ctx) {
    return (
      <Card title="Download">
        <Alert type="warning" showIcon message="Nothing to download" description="Open this from the Result screen after generating an arrangement." />
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => navigate("/production/result")}>← Back to Result</Button>
        </div>
      </Card>
    );
  }

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card title="Download plates">
        <Alert
          showIcon
          style={{ marginBottom: 16, background: alpha(colors.primary, 0.06), border: `1px solid ${alpha(colors.primary, 0.2)}` }}
          message={job ? `${plateNos.length} plate${plateNos.length === 1 ? "" : "s"} · ${job.action}` : "Loading arrangement…"}
          description={<Text type="secondary">Pick the plates and what to include, then download a .zip.</Text>}
        />

        {jobQ.isLoading && <div style={{ padding: 12 }}><Spin /></div>}
        {job && plateNos.length === 0 && <Empty description="This arrangement has no plates." />}

        {plateNos.length > 0 && (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <div>
              <div style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center" }}>
                <Text strong>Plates</Text>
                <ActionButton size="small" onClick={() => setSelected(plateNos)} disabled={selected.length === plateNos.length}>Select all</ActionButton>
                <ActionButton size="small" onClick={() => setSelected([])} disabled={selected.length === 0}>Clear</ActionButton>
              </div>
              <Checkbox.Group value={selected} onChange={(v) => setSelected(v as number[])}>
                <Space size={[8, 8]} wrap>
                  {plateNos.map((n) => (
                    <Checkbox key={n} value={n}>
                      Plate {n}
                      {names[String(n)] && (
                        <Tag style={{ marginLeft: 6, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>{names[String(n)]}</Tag>
                      )}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </div>

            <div>
              <div style={{ marginBottom: 8 }}><Text strong>Include</Text></div>
              <Radio.Group value={include} onChange={(e) => setInclude(e.target.value)}>
                <Radio.Button value="both">Data + Images</Radio.Button>
                <Radio.Button value="data" disabled={!hasExcel}>Data (Excel)</Radio.Button>
                <Radio.Button value="images">Images</Radio.Button>
              </Radio.Group>
              {!hasExcel && <div style={{ marginTop: 6 }}><Text type="secondary">Per-plate Excel is produced by the Compare and Max Coverage options.</Text></div>}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Button onClick={() => navigate("/production/result")}>← Back to Result</Button>
              <Button
                type="primary"
                icon={<FiDownload />}
                loading={downloadMut.isPending}
                disabled={!selected.length || !canDownload}
                onClick={() => downloadMut.mutate()}
              >
                Download {selected.length} plate{selected.length === 1 ? "" : "s"} (.zip)
              </Button>
            </div>
          </Space>
        )}
      </Card>
    </Space>
  );
}
