// ===================== FRONTEND: route registry =====================
// Routing is data, like the sidebar already is. Each feature ships a routes.ts
// exporting RouteEntry[]; App.tsx maps this list. Adding a module = adding its
// routes file to the imports below (the scaffold prints this step).

import type { ComponentType, LazyExoticComponent } from "react";

import { productionRoutes } from "../features/production/routes";

export interface RouteEntry {
  /** Form code the route is permission-gated on (matches acc_form.code). */
  form: string;
  /** Router path (relative to the authenticated root, no leading slash). */
  path: string;
  Component: LazyExoticComponent<ComponentType>;
}

export const ROUTES: RouteEntry[] = [
  ...productionRoutes,
];
