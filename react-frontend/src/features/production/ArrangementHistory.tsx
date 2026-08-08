// ===================== FRONTEND: Arrangement History =====================
// Read-only log of every arrangement run ever generated (TRN_SeedArrange). Sits
// directly below Seed Import in the sidebar. Each row is one run — the criteria it
// was generated with, how many plates it produced and its average fill. Opening a
// row shows that run's plates (fill %, seed counts, image + Excel links).
//
// Nothing here mutates: the records are written by the Result step when a job runs.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, Space, Typography, Alert, Drawer, Tag, Button, Spin, Empty, Descriptions, Row, Col, Image } from "antd";
import type { ColDef } from "ag-grid-community";
import { productionApi } from "./productionApi";
import type { ArrangementRow, ArrangementSeed } from "./types";
import { DataGrid } from "../../components/DataGrid";
import { FiInfo, FiEye, FiDownload, FiRefreshCw } from "../../components/icons";
import { colors, alpha } from "../../theme";

const { Text } = Typography;

/** Colour the method tag so Arrange / Max Coverage / Compare read apart at a glance. */
const METHOD_COLOR: Record<string, string> = {
  "Arrange": colors.primary,
  "Max Coverage": "#e67e22",
  "Compare": "#8e44ad",
  "Machine-Cut Fill": "#16a085",
  "Finalized": "#2c3e50",
};

function methodTag(method: string) {
  const c = METHOD_COLOR[method];
  if (!c) return <Tag style={{ margin: 0 }}>{method}</Tag>;
  return <Tag style={{ margin: 0, color: c, borderColor: alpha(c, 0.35), background: alpha(c, 0.08) }}>{method}</Tag>;
}

function pct(v: number | null | undefined) {
  return v === null || v === undefined ? "—" : `${v}%`;
}

const num = (v: number | null | undefined, suffix = "") => (v == null ? "—" : `${v}${suffix}`);

/** The seeds placed on a plate, shown under that plate's images. */
const SEED_COLS: ColDef<ArrangementSeed>[] = [
  { headerName: "Stock", field: "stock", minWidth: 140 },
  {
    headerName: "L × W (mm)",
    minWidth: 130,
    valueGetter: (p) => (p.data?.length == null ? "—" : `${p.data.length} × ${p.data.width}`),
  },
  { headerName: "Thick", field: "height", minWidth: 90, valueFormatter: (p) => num(p.value) },
  { headerName: "Cts", field: "cts", minWidth: 80, valueFormatter: (p) => num(p.value) },
  {
    headerName: "Type",
    field: "real",
    minWidth: 100,
    valueFormatter: (p) => (p.value ? "Real" : "Dummy"),
  },
];

/** Max Coverage also reports how much each boundary seat lost to the edge cut. */
const SEED_COLS_CUT: ColDef<ArrangementSeed>[] = [
  ...SEED_COLS,
  {
    headerName: "Cut off",
    field: "cutArea",
    minWidth: 130,
    valueGetter: (p) => (p.data?.cutArea == null ? "—" : `${p.data.cutArea} mm² (${p.data.cutPct}%)`),
  },
];

export function ArrangementHistory() {
  const [openId, setOpenId] = useState<string | null>(null);

  const listQ = useQuery({ queryKey: ["arrangements"], queryFn: productionApi.listArrangements });
  const detailQ = useQuery({
    queryKey: ["arrangement", openId],
    queryFn: () => productionApi.getArrangement(openId!),
    enabled: !!openId,
  });

  const rows = listQ.data ?? [];
  const detail = detailQ.data;

  const columns = useMemo<ColDef<ArrangementRow>[]>(
    () => [
      // Data columns are UNCAPPED on purpose. DataGrid gives every column flex: 1,
      // so they share the grid's width evenly; a maxWidth on all of them meant that
      // on a wide screen no column could grow and AG Grid left the remainder blank.
      // minWidth still guards readability — below their sum the grid scrolls.
      {
        // Sorted newest-first by the server on runAt (the header's date has no time).
        headerName: "Run at",
        field: "runAt",
        minWidth: 170,
        valueFormatter: (p) => {
          if (!p.value) return p.data?.entryDate?.slice(0, 10) ?? "—";
          const d = new Date(p.value);
          return Number.isNaN(d.getTime())
            ? String(p.value).slice(0, 10)
            : `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        },
      },
      {
        headerName: "Method",
        field: "method",
        minWidth: 150,
        cellRenderer: (p: { value: string }) => methodTag(p.value),
      },
      { headerName: "Plates", field: "plateCount", minWidth: 90 },
      {
        headerName: "Avg fill",
        field: "average",
        minWidth: 100,
        valueFormatter: (p) => pct(p.value),
      },
      {
        headerName: "Plate Ø",
        field: "plateDiameter",
        minWidth: 100,
        valueFormatter: (p) => (p.value == null ? "—" : `${p.value}mm`),
      },
      {
        headerName: "Thickness",
        minWidth: 130,
        valueGetter: (p) =>
          p.data?.thicknessMin == null ? "—" : `${p.data.thicknessMin}–${p.data.thicknessMax}mm`,
      },
      { headerName: "Shape", field: "shape", minWidth: 100 },
      {
        headerName: "Batches",
        minWidth: 100,
        valueGetter: (p) => p.data?.batches.length ?? 0,
      },
      {
        // The action column holds one fixed-size button — it stays capped so the
        // spare width goes to the data columns, and `Open` sits at the right edge.
        headerName: "",
        minWidth: 110,
        maxWidth: 120,
        sortable: false,
        filter: false,
        cellRenderer: (p: { data?: ArrangementRow }) =>
          p.data ? (
            <Button size="small" icon={<FiEye />} onClick={() => setOpenId(p.data!.arrangeId)}>
              Open
            </Button>
          ) : null,
      },
    ],
    [],
  );

  return (
    <Space direction="vertical" size="large" style={{ display: "flex" }}>
      <Card
        title="Arrangement History"
        extra={
          <Button size="small" icon={<FiRefreshCw />} loading={listQ.isFetching} onClick={() => listQ.refetch()}>
            Refresh
          </Button>
        }
      >
        <Alert
          showIcon
          icon={<FiInfo size={18} style={{ color: colors.primary }} />}
          style={{
            marginBottom: 16,
            background: alpha(colors.primary, 0.06),
            border: `1px solid ${alpha(colors.primary, 0.2)}`,
          }}
          message={listQ.isLoading ? "Loading…" : `${rows.length} arrangement${rows.length === 1 ? "" : "s"} recorded`}
          description={
            <Text type="secondary">
              Every run is kept here — the first arrange creates the first record and later runs are added, never
              overwritten. Open a row to see that run's plates.
            </Text>
          }
        />

        {listQ.isError && (
          <Alert type="error" showIcon message="Could not load arrangements" description={String(listQ.error)} />
        )}
        {!listQ.isLoading && !listQ.isError && rows.length === 0 && (
          <Empty description="No arrangements yet — run one from the Result screen." />
        )}
        {rows.length > 0 && <DataGrid rowData={rows} columnDefs={columns} pageSize={25} height={520} />}
      </Card>

      <Drawer
        open={!!openId}
        onClose={() => setOpenId(null)}
        width={900}
        title={detail ? `${detail.method} · ${detail.plates.length} plate${detail.plates.length === 1 ? "" : "s"}` : "Arrangement"}
      >
        {detailQ.isLoading && <div style={{ padding: 12 }}><Spin /></div>}
        {detail && (
          <Space direction="vertical" size="large" style={{ display: "flex" }}>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="Date">{detail.entryDate?.slice(0, 10) ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Method">{methodTag(detail.method)}</Descriptions.Item>
              <Descriptions.Item label="Average fill">{pct(detail.average)}</Descriptions.Item>
              <Descriptions.Item label="Seeds placed">{detail.seedCount}</Descriptions.Item>
              <Descriptions.Item label="Plate Ø">
                {detail.plateDiameter == null ? "—" : `${detail.plateDiameter}mm`}
              </Descriptions.Item>
              <Descriptions.Item label="Thickness">
                {detail.thicknessMin == null ? "—" : `${detail.thicknessMin}–${detail.thicknessMax}mm`}
              </Descriptions.Item>
              <Descriptions.Item label="Shape">{detail.shape ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Batches">{detail.batches.length}</Descriptions.Item>
            </Descriptions>

            {detail.plates.length === 0 ? (
              <Empty description="This run has no per-plate records (it predates plate tracking)." />
            ) : (
              detail.plates.map((p) => {
                // Show EVERY output this plate produced. A method is worth a block if it has
                // an image OR a seed list — older Max Coverage runs stored the seeds but no
                // image (that column didn't exist yet), and their list must still show.
                const known = [
                  { label: "Arrange", url: p.arrangeImageUrl, fill: p.arrangeFillPct },
                  { label: "Machine-Cut", url: p.machineImageUrl, fill: p.machineFillPct },
                  { label: "Max Coverage", url: p.enhancedImageUrl, fill: p.enhancedFillPct },
                  { label: "Finalized", url: p.finalizedImageUrl, fill: p.finalizedFillPct },
                ];
                const extra = Object.keys(p.seedsByMethod)
                  .filter((label) => !known.some((k) => k.label === label))
                  .map((label) => ({ label, url: null, fill: null }));
                const stages = [...known, ...extra].filter(
                  (s) => !!s.url || (p.seedsByMethod[s.label]?.length ?? 0) > 0,
                );

                return (
                  <div key={p.plateNo} style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 12 }}>
                    <Space wrap style={{ marginBottom: 10 }}>
                      <Text strong>Plate {p.plateNo}</Text>
                      {p.plateName && (
                        <Tag style={{ margin: 0, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>
                          {p.plateName}
                        </Tag>
                      )}
                      <Text type="secondary">
                        {p.realSeedCount ?? 0} seed{p.realSeedCount === 1 ? "" : "s"}
                        {p.dummyCount ? ` · ${p.dummyCount} dummy` : ""}
                      </Text>
                      {p.excelUrl && (
                        <Button size="small" icon={<FiDownload />} href={p.excelUrl} target="_blank">
                          Excel
                        </Button>
                      )}
                    </Space>

                    {stages.length === 0 ? (
                      <Text type="secondary">No images or seed lists recorded for this plate.</Text>
                    ) : (
                      <Space direction="vertical" size="middle" style={{ display: "flex" }}>
                        {stages.map((s) => {
                          // Each method keeps its own seed list — Max Coverage packs more,
                          // trimmed, seats than Arrange, so the two lists genuinely differ.
                          const seeds = p.seedsByMethod[s.label] ?? [];
                          const trimmed = seeds.filter((x) => x.cutArea != null).length;
                          return (
                            <div key={s.label} style={{ border: `1px solid ${colors.border}`, borderRadius: 6, padding: 10 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                                {methodTag(s.label === "Machine-Cut" ? "Machine-Cut Fill" : s.label)}
                                {s.fill != null && <Text type="secondary">{pct(s.fill)} filled</Text>}
                                {seeds.length > 0 && (
                                  <Text type="secondary">
                                    {seeds.length} seed{seeds.length === 1 ? "" : "s"}
                                    {trimmed > 0 ? ` · ${trimmed} trimmed at the edge` : ""}
                                  </Text>
                                )}
                                {!s.url && <Tag style={{ margin: 0 }}>no image saved</Tag>}
                              </div>
                              <Row gutter={[12, 12]}>
                                {s.url && (
                                  <Col xs={24} lg={10}>
                                    <Image
                                      src={s.url}
                                      alt={`Plate ${p.plateNo} ${s.label}`}
                                      width="100%"
                                      style={{ objectFit: "contain", borderRadius: 4 }}
                                    />
                                    <div style={{ marginTop: 6 }}>
                                      <Button size="small" icon={<FiEye />} href={s.url} target="_blank">
                                        Open full size
                                      </Button>
                                    </div>
                                  </Col>
                                )}
                                {/* Without an image the table takes the full width. */}
                                <Col xs={24} lg={s.url ? 14 : 24}>
                                  {seeds.length === 0 ? (
                                    <Text type="secondary">No seed list stored for this method.</Text>
                                  ) : (
                                    <DataGrid
                                      rowData={seeds}
                                      columnDefs={trimmed > 0 ? SEED_COLS_CUT : SEED_COLS}
                                      autoHeight
                                      paginated={false}
                                    />
                                  )}
                                </Col>
                              </Row>
                            </div>
                          );
                        })}
                      </Space>
                    )}
                  </div>
                );
              })
            )}
          </Space>
        )}
      </Drawer>
    </Space>
  );
}
