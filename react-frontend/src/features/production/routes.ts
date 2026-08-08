// Route entries for the production feature (see routes/registry.ts).
// Paths and form codes mirror modules/production/catalogue.py — the sidebar
// navigates to the form's `route`, so the two must agree.
import { lazy } from "react";
import type { RouteEntry } from "../../routes/registry";

export const productionRoutes: RouteEntry[] = [
  { form: "seed_import", path: "production/seed-import", Component: lazy(() => import("./SeedImport").then((m) => ({ default: m.SeedImport }))) },
  { form: "arrangement_history", path: "production/arrangements", Component: lazy(() => import("./ArrangementHistory").then((m) => ({ default: m.ArrangementHistory }))) },
  { form: "plate_master", path: "production/plate-master", Component: lazy(() => import("./PlateMaster").then((m) => ({ default: m.PlateMaster }))) },
  { form: "batch_selection", path: "production/batch-selection", Component: lazy(() => import("./BatchSelection").then((m) => ({ default: m.BatchSelection }))) },
  { form: "criteria_input", path: "production/criteria", Component: lazy(() => import("./CriteriaInput").then((m) => ({ default: m.CriteriaInput }))) },
  { form: "processing_option", path: "production/processing-option", Component: lazy(() => import("./ProcessingOption").then((m) => ({ default: m.ProcessingOption }))) },
  { form: "result_generation", path: "production/result", Component: lazy(() => import("./ResultGeneration").then((m) => ({ default: m.ResultGeneration }))) },
  { form: "finalization", path: "production/finalize", Component: lazy(() => import("./Finalization").then((m) => ({ default: m.Finalization }))) },
  { form: "download", path: "production/download", Component: lazy(() => import("./DownloadPlates").then((m) => ({ default: m.DownloadPlates }))) },
];
