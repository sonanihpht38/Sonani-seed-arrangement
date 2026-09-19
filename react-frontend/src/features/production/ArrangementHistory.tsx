// ===================== FRONTEND: Arrangement History =====================
// Read-only log of every arrangement run ever generated (TRN_SeedArrange). Sits
// directly below Seed Import in the sidebar. Each row is one run — the criteria it
// was generated with, how many plates it produced and its average fill. Opening a
// row shows that run's plates (fill %, seed counts, image + Excel links).
//
// Nothing here mutates: the records are written by the Result step when a job runs.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Space, Typography, Alert, Drawer, Tag, Button, Spin, Empty, Descriptions, Row, Col, Image, Select, Modal, Form, Input, InputNumber, Switch } from "antd";
import type { ColDef } from "ag-grid-community";
import { useAuth } from "../auth/useAuth";
import { productionApi } from "./productionApi";
import { notify } from "../../lib/notify";
import { mediaUrl } from "../../lib/media";
import type { ArrangementPlate, ArrangementRow, ArrangementSeed } from "./types";
import { DataGrid } from "../../components/DataGrid";
import { FiInfo, FiEye, FiDownload, FiRefreshCw, FiCheck, FiPlus } from "../../components/icons";
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

// ---- Which layout a plate actually gets built from ------------------------
// Mirrors InventoryService.BUILT_METHOD / seed_ids_for on the server: a Compare
// run records a placement per method, and naming the plate commits the Max
// Coverage one — that is the layout the floor builds.
//
// The fallback to other methods is decided ONCE FOR THE RUN, matching the
// server: a Compare run whose Max Coverage pass ran out of stock ends with
// Arrange-only plates, and those hold no stones of their own — their seeds are
// already drawn onto earlier Max Coverage plates. Falling back per plate would
// report seeds that naming the plate cannot legally take.
//
// This is REPORTING only. It reads the seed lists already in the detail
// response and changes nothing about what Assign consumes.
const BUILT_LABEL = "Max Coverage";

/** True when ANY plate of the run has a Max Coverage layout. */
function runHasBuiltLayout(plates: ArrangementPlate[]) {
  return plates.some((p) => (p.seedsByMethod[BUILT_LABEL] ?? []).some((s) => s.real));
}

/** The seeds naming this plate will consume, and the layout they come from.
 *  `excluded` mirrors InventoryService.excluded_from_built_layout: the plate
 *  placed seeds, but none in the built layout, so the server refuses to name
 *  it. A plate with no seed rows AT ALL is not excluded — it consumed nothing
 *  before this rule and still does. */
function builtSeeds(
  p: ArrangementPlate,
  runHasBuilt: boolean,
): { count: number; label: string | null; excluded: boolean } {
  const built = p.seedsByMethod[BUILT_LABEL]?.filter((s) => s.real) ?? [];
  if (runHasBuilt) {
    const placed = Object.values(p.seedsByMethod).some((l) => l.some((s) => s.real));
    return { count: built.length, label: BUILT_LABEL, excluded: !built.length && placed };
  }
  // The run has no Max Coverage layout anywhere. The server then consumes the
  // union of every method's rows, de-duplicated by seed — Stock No is the
  // per-seed key we have here.
  const stocks = new Set<string>();
  for (const seeds of Object.values(p.seedsByMethod)) {
    for (const s of seeds) if (s.real) stocks.add(s.stock);
  }
  // Pre-plate-tracking runs have no seed lists at all; the stored count is then
  // the only number there is.
  return { count: stocks.size || (p.realSeedCount ?? 0), label: null, excluded: false };
}

/** Seed-width band as text. Both ends null = no band was set on that run. */
function widthBandText(lo: number | null, hi: number | null) {
  if (lo == null && hi == null) return "—";
  if (lo != null && hi != null) return `${lo}–${hi}mm`;
  return lo != null ? `≥ ${lo}mm` : `≤ ${hi}mm`;
}

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
  const { can } = useAuth();
  // Naming a plate consumes inventory, so it needs the same permission the
  // Finalization screen asks for.
  const canAssign = can("finalization", "save");
  const qc = useQueryClient();

  const listQ = useQuery({ queryKey: ["arrangements"], queryFn: productionApi.listArrangements });
  const detailQ = useQuery({
    queryKey: ["arrangement", openId],
    queryFn: () => productionApi.getArrangement(openId!),
    enabled: !!openId,
  });

  // ---- Assign a plate name from HERE -------------------------------------
  // The normal route is Result -> Finalize, and a user who skipped it had no way
  // back once the job had expired: this screen reads TRN_SeedPlate, so it is the
  // one place a past run is still reachable. Assigning only — RELEASING stays in
  // Finalization, which is where the per-plate inventory view lives.
  const availQ = useQuery({
    queryKey: ["available-plates"],
    queryFn: productionApi.availablePlates,
    enabled: !!openId,
  });
  const [pick, setPick] = useState<Record<number, string | undefined>>({});
  const assignMut = useMutation({
    mutationFn: (v: { plateNo: number; plateName: string }) =>
      productionApi.assignPlate(openId!, v.plateNo, v.plateName),
    onSuccess: (r) => {
      notify.success(
        `Named "${r.plateName}" — ${r.seedsConsumed} seeds removed from the available list.`);
      detailQ.refetch();
      availQ.refetch();
      qc.invalidateQueries({ queryKey: ["arrangements"] });
      qc.invalidateQueries({ queryKey: ["finalized-plates"] });
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Assign failed"),
  });
  const nameOptions = useMemo(
    () => (availQ.data ?? [])
      .filter((p) => !p.isUsed)
      .map((p) => ({ value: p.plateName, label: p.plateName }))
      .sort((a, b) => a.label.localeCompare(b.label)),
    [availQ.data]);

  // ---- Add a plate the master doesn't have yet ----------------------------
  // The picker above can only offer plates that already exist, so a run that
  // needs a plate nobody has entered was a dead end: leave the drawer, go to
  // Plate Master, add it, come back, find the run again. This is the same
  // create, reached from the place the need is discovered.
  //
  // It posts to the Plate Master endpoint — NOT a new one — so the row is built
  // by the same serializer, the same validation and the same permission as the
  // Plate Master screen's own "New plate". Nothing about assigning, consuming or
  // releasing changes: this only puts a name in the pool, and the existing
  // Assign button then does exactly what it did before.
  const canCreatePlate = can("plate_master", "save");
  const [newFor, setNewFor] = useState<number | null>(null);
  const [plateForm] = Form.useForm();
  const createMut = useMutation({
    mutationFn: (v: { plate_name: string; diameter?: number | null; is_active: boolean }) =>
      productionApi.createPlate(v),
    onSuccess: (created) => {
      notify.success(`Plate "${created.plate_name}" added to Plate Master.`);
      // Drop it straight into this plate's picker so the user just clicks
      // Assign — the reason they opened the dialog in the first place.
      if (newFor !== null) setPick((s) => ({ ...s, [newFor]: created.plate_name }));
      setNewFor(null);
      plateForm.resetFields();
      availQ.refetch();
      qc.invalidateQueries({ queryKey: ["plate-master"] });
    },
    onError: (e) => notify.error(e instanceof Error ? e.message : "Could not add the plate"),
  });

  /** Open the dialog for one plate of this run, sized to match the run. */
  function openNewPlate(plateNo: number) {
    setNewFor(plateNo);
    // The run knows the diameter it was packed for, so offer it rather than
    // making the user re-type a number the screen already shows. Editable —
    // it is a default, not a rule.
    plateForm.setFieldsValue({
      plate_name: "",
      diameter: detailQ.data?.plateDiameter ?? null,
      is_active: true,
    });
  }

  const rows = listQ.data ?? [];
  const detail = detailQ.data;
  // Decided for the whole run, not per plate — see builtSeeds above.
  const runHasBuilt = useMemo(
    () => runHasBuiltLayout(detail?.plates ?? []),
    [detail],
  );

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
        // How much inventory this run is holding — REPORTED here, never changed.
        //
        // A "Return" button lived in this cell and has been removed. It called
        // DELETE on the unfinalize route, and live serves the app through IIS,
        // whose WebDAV module answers DELETE with 405 before Django is reached —
        // so it could never work there. It also offered a second way to hand
        // stock back that disagreed with the first: this one freed a whole run
        // at once, while Finalization frees one plate at a time. Releasing is
        // now a single action in a single place: Finalization, per plate, POST.
        headerName: "Seeds held",
        field: "seedsHeld",
        minWidth: 130,
        cellRenderer: (p: { data?: ArrangementRow }) => {
          const n = p.data?.seedsHeld ?? 0;
          if (!p.data) return null;
          if (!n) return <Text type="secondary">—</Text>;
          return <Tag color="green" style={{ margin: 0 }}>{n}</Tag>;
        },
      },
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
      {
        // Seed-width band the run used. "—" covers both "no band set" and every
        // run made before the criteria form had the field, which are the same
        // thing: the whole thickness window was eligible.
        headerName: "Seed width",
        minWidth: 130,
        valueGetter: (p) => widthBandText(p.data?.widthMin ?? null, p.data?.widthMax ?? null),
      },
      { headerName: "Shape", field: "shape", minWidth: 100 },
      {
        // The batch NAMES, not a count. A bare "1" told you how many batches fed
        // the run but never which — and which is the thing anyone looking at a
        // past run actually wants. These are the batches SELECTED for the run;
        // open the row for the per-plate breakdown, which differs once a run
        // makes more than one plate.
        headerName: "Batches",
        minWidth: 150,
        valueGetter: (p) =>
          p.data?.batches?.length ? p.data.batches.join(", ") : "—",
        tooltipValueGetter: (p) => p.data?.batches?.join(", ") ?? "",
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canAssign],
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
        {/* No explicit height: the grid fills the viewport (see DataGrid), so a
            big screen shows many more runs than the old fixed 520 px box. */}
        {rows.length > 0 && <DataGrid rowData={rows} columnDefs={columns} pageSize={25} />}
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
              <Descriptions.Item label="Seed width">
                {widthBandText(detail.widthMin, detail.widthMax)}
              </Descriptions.Item>
              <Descriptions.Item label="Shape">{detail.shape ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Batches">{detail.batches.length}</Descriptions.Item>
            </Descriptions>

            {detail.plates.length === 0 ? (
              <Empty description="This run has no per-plate records (it predates plate tracking)." />
            ) : (
              detail.plates.map((p) => {
                // What naming this plate will actually take out of inventory.
                const build = builtSeeds(p, runHasBuilt);
                // An Arrange-only tail plate of a Compare run: its stones sit on
                // earlier plates, so the server refuses to name it. Don't offer to.
                const notBuilt = build.excluded;
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
                      {/* Which batch this PLATE's stones came from. The run-level
                          count in the header says how many batches were selected;
                          with several plates that is not the same question. */}
                      {p.batches?.length ? (
                        <Tag
                          style={{
                            margin: 0,
                            color: colors.violet,
                            borderColor: alpha(colors.violet, 0.35),
                            background: alpha(colors.violet, 0.08),
                          }}
                        >
                          {p.batches.length > 1 ? "Batches" : "Batch"} {p.batches.join(", ")}
                        </Tag>
                      ) : null}
                      {p.plateName ? (
                        <Tag style={{ margin: 0, color: colors.primary, borderColor: alpha(colors.primary, 0.35), background: alpha(colors.primary, 0.08) }}>
                          {p.plateName}
                        </Tag>
                      ) : notBuilt ? (
                        // Its stones are already on earlier Max Coverage plates,
                        // so naming it would commit them twice. Say so instead of
                        // offering a control the server will refuse.
                        <Tag style={{ margin: 0 }}>not in the built layout</Tag>
                      ) : canAssign ? (
                        // The second chance at naming a plate. Assign only: this
                        // consumes the seeds, and handing them back stays in
                        // Finalization where the inventory view is.
                        <>
                          <Select
                            showSearch
                            allowClear
                            size="small"
                            style={{ width: 200 }}
                            placeholder="Assign a plate name…"
                            value={pick[p.plateNo]}
                            onChange={(v) => setPick((s) => ({ ...s, [p.plateNo]: v }))}
                            options={nameOptions}
                            loading={availQ.isLoading}
                            notFoundContent={
                              <Text type="secondary">
                                {canCreatePlate
                                  ? "No free plates in the master — use New plate."
                                  : "No free plates in the master."}
                              </Text>
                            }
                          />
                          {canCreatePlate && (
                            <Button size="small" icon={<FiPlus />} onClick={() => openNewPlate(p.plateNo)}>
                              New plate
                            </Button>
                          )}
                          <Button
                            size="small"
                            type="primary"
                            icon={<FiCheck />}
                            loading={assignMut.isPending && assignMut.variables?.plateNo === p.plateNo}
                            disabled={!pick[p.plateNo]}
                            onClick={() => assignMut.mutate({
                              plateNo: p.plateNo, plateName: pick[p.plateNo]! })}
                          >
                            Assign
                          </Button>
                        </>
                      ) : null}
                      {/* The count of the layout that gets BUILT, not the stored
                          RealSeedCount. For a Compare run that column is written
                          from the Arrange pass, so it disagreed with the seeds
                          Assign consumes — 10 shown against 13 taken, on most
                          Compare plates. The number below is the one the server
                          acts on. */}
                      <Text type="secondary">
                        {build.count} seed{build.count === 1 ? "" : "s"}
                        {p.dummyCount ? ` · ${p.dummyCount} dummy` : ""}
                      </Text>
                      {/* Say which of a Compare plate's layouts that is. With one
                          layout there is nothing to disambiguate, so it is left
                          off rather than repeated on every plate. */}
                      {build.label && stages.length > 1 ? (
                        <Tag
                          style={{
                            margin: 0,
                            color: colors.primary,
                            borderColor: alpha(colors.primary, 0.35),
                            background: alpha(colors.primary, 0.08),
                          }}
                        >
                          Builds: {build.label}
                        </Tag>
                      ) : null}
                      {p.excelUrl && (
                        <Button size="small" icon={<FiDownload />} href={mediaUrl(p.excelUrl)} target="_blank">
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
                                {/* Point the plate header's Assign button at the
                                    panel it belongs to. The header sits above the
                                    FIRST panel, which made a per-plate control
                                    read as if it were Arrange's. */}
                                {stages.length > 1 && s.label === build.label ? (
                                  <Tag
                                    style={{
                                      margin: 0,
                                      color: colors.primary,
                                      borderColor: alpha(colors.primary, 0.35),
                                      background: alpha(colors.primary, 0.08),
                                    }}
                                  >
                                    {p.plateName ? "built from this" : "Assign builds this"}
                                  </Tag>
                                ) : null}
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
                                      src={mediaUrl(s.url)}
                                      alt={`Plate ${p.plateNo} ${s.label}`}
                                      width="100%"
                                      style={{ objectFit: "contain", borderRadius: 4 }}
                                    />
                                    <div style={{ marginTop: 6 }}>
                                      <Button size="small" icon={<FiEye />} href={mediaUrl(s.url)} target="_blank">
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

      {/* Same fields, same rules and same endpoint as Plate Master's own "New
          plate" dialog — deliberately, so a plate created here is in every way
          an ordinary plate afterwards: it lists, edits, deactivates, assigns
          and releases exactly like one entered on that screen. */}
      <Modal
        title="New plate"
        open={newFor !== null}
        onCancel={() => { setNewFor(null); plateForm.resetFields(); }}
        onOk={() => plateForm.submit()}
        confirmLoading={createMut.isPending}
        okText="Add plate"
      >
        <Form
          form={plateForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(v) => createMut.mutate(v)}
        >
          <Form.Item name="plate_name" label="Plate name" rules={[{ required: true, message: "Required" }]}>
            <Input placeholder="e.g. P2-90" maxLength={50} />
          </Form.Item>
          <Form.Item
            name="diameter"
            label="Diameter (mm)"
            extra="Pre-filled from this run — change it if the physical plate differs."
          >
            <InputNumber min={0} step={1} style={{ width: "100%" }} placeholder="e.g. 90" />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
