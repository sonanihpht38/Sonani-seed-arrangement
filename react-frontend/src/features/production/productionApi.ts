// Feature API layer for the production module — maps UI intents to endpoints.
// Seed import is a multipart upload (the datasheet), so it goes through the
// client's postForm helper; the audit user is taken from the JWT server-side.

import { api } from "../../api/client";
import type {
  Action, ArrangementDetail, ArrangementRow, AvailablePlate, Batch, CreateJobResult, FinalPlate,
  FinalizeStatus, FinalizedPlate, ImportResult, Job, SeedPlate,
} from "./types";

type PlateInput = { plate_name: string; diameter?: number | null; is_active?: boolean };

export const productionApi = {
  importSeeds: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.postForm<ImportResult>("/production/seeds/import/", form);
  },

  listBatches: () => api.get<Batch[]>("/production/batches/"),

  // Start an arrange / machinefill / compare job over the seeds in TRN_SeedData.
  createJob: (action: Action, params: Record<string, unknown>) =>
    api.post<CreateJobResult>("/production/jobs", { action, params }),

  getJob: (id: string) => api.get<Job>(`/production/jobs/${id}`),

  // Finalize (Form 6): regenerate finalized plate images + per-plate name assignment.
  generateFinal: (jobId: string) =>
    api.post<{ plates: FinalPlate[] }>(`/production/jobs/${jobId}/generate-final`, {}),

  getPlateNames: (arrangeId: string) =>
    api.get<{ names: Record<string, string | null> }>(`/production/arrangements/${arrangeId}/plate-names`),

  // Arrangement History: every past run, and the plates of one run.
  listArrangements: () => api.get<ArrangementRow[]>("/production/arrangements/"),

  getArrangement: (arrangeId: string) =>
    api.get<ArrangementDetail>(`/production/arrangements/${arrangeId}`),

  // Assigning a name finalizes that plate: its seeds leave the available pool.
  // Releasing gives them back. Both counts come back so the UI can say so.
  assignPlate: (arrangeId: string, plateNo: number, plateName: string) =>
    api.post<{ assigned: boolean; plateName: string | null; seedsConsumed: number }>(
      "/production/plates/assign", { arrangeId, plateNo, plateName }),

  releasePlate: (arrangeId: string, plateNo: number) =>
    api.post<{ released: boolean; plateName: string | null; seedsReturned: number }>(
      "/production/plates/release", { arrangeId, plateNo }),

  // Finalizing a whole arrangement consumes its seeds: they stop appearing in
  // later runs until the arrangement is unfinalized.
  finalizeStatus: (arrangeId: string) =>
    api.get<FinalizeStatus>(`/production/arrangements/${arrangeId}/finalize`),
  // Recovery only: hands back every seed the run is holding, whichever plate
  // took it. Normal flow is per plate, via assign / release.
  unfinalizeArrangement: (arrangeId: string) =>
    api.del<{ finalized: boolean; returned: number }>(
      `/production/arrangements/${arrangeId}/finalize`),

  // Download (Form 7): zip of the selected plates' data (Excel) and/or images.
  downloadPlates: (jobId: string, plateNos: number[], include: "data" | "images" | "both") =>
    api.postBlob(`/production/jobs/${jobId}/download`, { plateNos, include }),

  // Plate Master (MST_SeedPlate inventory) — CRUD.
  listPlateMaster: () => api.get<SeedPlate[]>("/production/plate-master/"),
  createPlate: (p: PlateInput) => api.post<SeedPlate>("/production/plate-master/", p),
  updatePlate: (id: number, p: PlateInput) => api.put<SeedPlate>(`/production/plate-master/${id}/`, p),
  deletePlate: (id: number) => api.del<void>(`/production/plate-master/${id}/`),
  // Unassign from the Plate Master screen. Finalization's releasePlate needs an
  // arrangement; this one works from the plate alone, which is all this screen has.
  releasePlateById: (id: number) =>
    api.post<{ released: boolean; plateName: string | null; clearedFrom: number }>(
      `/production/plate-master/${id}/release/`, {}),

  // Plate names available to assign in Finalization (from the master pool).
  availablePlates: () => api.get<AvailablePlate[]>("/production/plates"),

  // Every plate already finalized. Read from the database, so it does not need
  // the run that produced a plate to still be open.
  finalizedPlates: () => api.get<FinalizedPlate[]>("/production/plates/finalized"),
};
