import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the Django backend so the app can use relative URLs
// (client.ts falls back to "/api" when VITE_API_URL is unset). No CORS headaches
// in development.
//
// Port 8001, not 8000: other Django projects on this machine default to 8000, and
// whichever backend binds it first silently captures this app's API traffic — you
// get someone else's sidebar and data with no error anywhere. Override with
// API_PROXY_TARGET when you need to point somewhere else.
const API_TARGET = process.env.API_PROXY_TARGET || "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind every interface so the app is reachable from the LAN (e.g.
    // http://192.168.10.83:5174), not just from this machine. Only THIS port is
    // exposed: Django stays on 127.0.0.1 and everything below reaches it through
    // this proxy, so the backend is never directly addressable from the network.
    host: true,
    // Honor an externally assigned port (preview/CI tooling); default 5174.
    // 5173 is taken by the other project on this machine.
    port: Number(process.env.PORT) || 5174,
    // Anything NOT listed here falls through to Vite's SPA fallback, which answers
    // index.html with a 200 — a missing entry looks like a working page, not a 404.
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
      // The production module's generated plate images / Excel are served by the
      // backend under /media. Without this the browser asks Vite for them, gets
      // index.html back, and every <img> renders broken.
      "/media": {
        target: API_TARGET,
        changeOrigin: true,
      },
      // Django admin. Since the Administration module was removed, this is the
      // ONLY place to create users, activate registrations and assign roles — so
      // it has to be reachable from wherever the administrator sits, not just
      // from the host running Django.
      //
      // changeOrigin rewrites Host to the target; the browser's Origin header is
      // passed through untouched, so Django's CSRF check on the login POST needs
      // this app's origin in CSRF_TRUSTED_ORIGINS (see django-backend/.env).
      "/admin": {
        target: API_TARGET,
        changeOrigin: true,
      },
      // The admin's CSS/JS. Served by WhiteNoise from STATIC_ROOT (DEBUG is off),
      // so `manage.py collectstatic` must have been run or the admin renders bare.
      "/static": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    // No source maps in the shipped bundle (smaller, don't leak source).
    sourcemap: false,
    // Split rarely-changing vendor code into its own chunk so app-code deploys
    // don't bust the (long-cached) vendor chunk for returning users.
    rollupOptions: {
      output: {
        // Split large, rarely-changing vendors into their own long-cached chunks.
        // ag-grid is only pulled in by the lazy feature screens, so its chunk
        // loads on demand — not on first paint.
        // MATCH BY PATH, not by package name. The object form
        // ({"react-vendor": ["react", "react-dom", ...]}) matches only the exact
        // ids listed, so `react-dom/client`, `scheduler` and antd's `rc-*`
        // internals were never claimed and scattered into whichever chunk first
        // pulled them — react-dom ended up inside antd-vendor.
        //
        // That made the two vendor chunks CIRCULAR: react-vendor holds
        // react-router-dom, which imports react-dom (then in antd-vendor), while
        // antd-vendor imports React from react-vendor. Whichever chunk evaluated
        // first saw the other's exports as undefined, and the app died on
        // `React.__SECRET_INTERNALS_...` of undefined — a blank white page with
        // one console error and no other clue.
        //
        // Matching on the node_modules path keeps react + react-dom + scheduler
        // together, so the dependency runs one way: antd/ag-grid -> react-vendor.
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          const p = id.replace(/\\/g, "/");
          if (/\/node_modules\/(react|react-dom|scheduler|react-router|react-router-dom|@remix-run|@tanstack)\//.test(p)) {
            return "react-vendor";
          }
          if (/\/node_modules\/(antd|@ant-design|rc-[^/]+|@rc-component)\//.test(p)) {
            return "antd-vendor";
          }
          if (/\/node_modules\/(ag-grid-community|ag-grid-react)\//.test(p)) {
            return "aggrid-vendor";
          }
        },
      },
    },
    chunkSizeWarningLimit: 1000,
  },
});
