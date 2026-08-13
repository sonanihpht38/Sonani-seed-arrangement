// TypeScript mirror of the production module DTOs (serializers.py).
// Seed import parses an Excel datasheet into TRN_SeedData, auto-creating batches
// and skipping duplicate stock numbers.

export interface SkippedSeed {
  stock_no: string;
  batch_no: string | null;
  reason: string; // "Entry already exists" | "Duplicate row in sheet"
}

// A batch touched by an import, with how many seeds landed in it this run.
export interface ImportedBatch {
  batch_no: string | null;
  imported_count: number;
  is_new: boolean;
}

export interface ImportResult {
  imported: number;
  skipped_count: number;
  skipped: SkippedSeed[];
  batches_created: string[];
  batches: ImportedBatch[];
}

// A batch with its seed count — for the Batch Selection screen.
export interface Batch {
  batch_id: string;
  batch_no: string | null;
  seed_count: number;
  is_active: boolean;
}

export type Shape = "all" | "square" | "rectangle";

// The processing option chosen in Form 4 — maps to the arrangement job's action.
export type Action = "arrange" | "machinefill" | "compare" | "enhanced";

// ---- Arrangement History (every past run, from TRN_SeedArrange) ----

// One past arrangement run. `method` is derived server-side from the artifacts the
// run wrote ("—" for old runs saved before per-plate rows existed).
export interface ArrangementRow {
  arrangeId: string;
  method: string;
  mode: string | null;
  shape: string | null;
  plateCount: number;
  average: number | null;
  plateDiameter: number | null;
  thicknessMin: number | null;
  thicknessMax: number | null;
  batches: string[];
  entryDate: string | null;
  /** Real run timestamp (from the plate rows) — the header's EntryDate is date-only. */
  runAt?: string | null;
  isFinalized: boolean;
  /** Seeds this run is holding (TRN_SeedData.Used_ID) — 0 once they are returned. */
  seedsHeld: number;
}

// One placed seed on a past run's plate (real seed, or a Machine-Cut dummy filler).
export interface ArrangementSeed {
  stock: string;
  length: number | null;
  width: number | null;
  height: number | null;
  cts: number | null;
  /** Max Coverage only: how much of the seat the edge cut removed. null = whole seed. */
  cutArea: number | null;
  cutPct: number | null;
  real: boolean;
}

// One plate inside a past run.
export interface ArrangementPlate {
  plateNo: number;
  plateName: string | null;
  arrangeFillPct: number | null;
  machineFillPct: number | null;
  enhancedFillPct: number | null;
  finalizedFillPct: number | null;
  realSeedCount: number | null;
  dummyCount: number | null;
  arrangeImageUrl: string | null;
  machineImageUrl: string | null;
  enhancedImageUrl: string | null;
  finalizedImageUrl: string | null;
  excelUrl: string | null;
  /** One seed list per method, keyed by the same label as that method's plate image. */
  seedsByMethod: Record<string, ArrangementSeed[]>;
}

export interface ArrangementDetail extends Omit<ArrangementRow, "plateCount"> {
  seedCount: number;
  plates: ArrangementPlate[];
}

// Per-seed dimension row shown in a plate's detail table.
export interface DimRow {
  type: string;
  stock: string;
  size: string;
  thick: string;
  shape: string;
  cut?: string;
  center: string;
  real: boolean;
}

// A single-stage plate (Arrange OR Machine-Cut Fill).
export interface PlateView {
  plateNo: number;
  fillPct: number;
  imageUrl: string;
  seeds: DimRow[];
  dummyCount?: number;
  exportUrl?: string; // per-plate Excel (Enhanced Version)
}

// One method's panel inside a Compare plate.
export interface PanelView {
  method: "arrange" | "machinefill" | "enhanced";
  label: string;
  fillPct: number;
  imageUrl: string;
  seeds: DimRow[];
  dummyCount: number;
}

// A Compare plate: the user-selected methods (2 or 3) side by side, with a per-plate Excel.
export interface PairView {
  plateNo: number;
  methods: string[];
  panels: PanelView[];
  exportUrl: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: string;
  action: Action;
  status: JobStatus;
  progress: number;
  error: string | null;
  plates: PlateView[];
  pairs: PairView[];
  arrangeAvg: number;
  machineAvg: number;
  enhancedAvg: number;
  arrangeId: string | null;
  seedsMatched: number | null;
}

export interface CreateJobResult {
  id: string;
}

// A finalized plate (Form 6): kept reals + any replacements/empties, re-rendered.
export interface FinalPlate {
  plateNo: number;
  fillPct: number;
  imageUrl: string;
  altCount: number;
  dummyCount: number;
  emptyCount: number;
  seeds: DimRow[];
  plateName: string;
}

// Handoff from the Result screen's "Finalize this plate" button.
export interface FinalizeContext {
  jobId: string;
  arrangeId: string;
  plateNo: number;
}

// MST_SeedPlate row — the plate-name inventory master (Plate Master form).
export interface SeedPlate {
  plate_id: number;
  plate_name: string;
  diameter: number | null;
  is_active: boolean;
  is_used: boolean;
  is_released: boolean;
}

// A plate name available to assign in Finalization (from the master pool).
export interface AvailablePlate {
  plateId: number;
  plateName: string;
  diameter: number | null;
  isUsed: boolean;
  isReleased: boolean;
}

// Finalization state of one arrangement, plus what it means for inventory.
// A finalized run's seeds are consumed: they no longer reach the packer.
export interface FinalizeStatus {
  arrangeId: string;
  isFinalized: boolean;          // every plate of this run is named
  plates: {
    plateNo: number;
    plateName: string | null;
    seeds: number;
    consumed: boolean;
    takenElsewhere: number;   // seeds another run has committed — >0 means stale
    canAssign: boolean;
  }[];
  seedsInArrangement: number;
  seedsConsumedByThisRun: number;
  seedsAvailable: number;
  seedsUsedTotal: number;
}

// A plate that has been finalized — one row of TRN_SeedPlate carrying a name.
export interface FinalizedPlate {
  plateName: string;
  plateId: number | null;
  plateNo: number | null;
  arrangeId: string | null;
  seeds: number;
  fillPct: number | null;
  plateDiameter: number | null;
  imageUrl: string | null;
  finalizedAt: string | null;
}

// The packing criteria collected in Form 3 and used by the arrangement job.
// Field names match the engine's job params. mode is fixed "mixed"; squareTol,
// clearance and grid are fixed to 0.
export interface Criteria {
  mode: "mixed";
  shape: Shape;
  squareTol: number;
  tLo: number;
  tHi: number;
  plateD: number;
  margin: number;
  minSeed: number;
  clearance: number;
  grid: number;
}
