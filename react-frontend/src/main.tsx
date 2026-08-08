import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntApp } from "antd";
import { BrowserRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";

import { App } from "./App";
import { AuthProvider } from "./features/auth/useAuth";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { queryClient } from "./api/queryClient";
import { antdTheme } from "./theme";

import "antd/dist/reset.css";
import "react-toastify/dist/ReactToastify.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider theme={antdTheme}>
          <AntApp>
            <BrowserRouter>
              <AuthProvider>
                <App />
              </AuthProvider>
            </BrowserRouter>
            <ToastContainer position="top-right" autoClose={3000} newestOnTop theme="colored" />
          </AntApp>
        </ConfigProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
