import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import { Layout } from "./components/Layout";
import { DayDrawerProvider } from "./components/DayDrawer";
import { SquadPage } from "./pages/Squad";
import { AthletePage } from "./pages/Athlete";
import { CalendarPage } from "./pages/Calendar";
import { DailyPage } from "./pages/Daily";
import { QualityPage } from "./pages/Quality";
import { ForecastPage } from "./pages/Forecast";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false, retry: 1 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <DayDrawerProvider>
          <Layout>
            <Routes>
              <Route path="/" element={<SquadPage />} />
              <Route path="/athlete/:id" element={<AthletePage />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/daily" element={<DailyPage />} />
              <Route path="/quality" element={<QualityPage />} />
              <Route path="/forecast" element={<ForecastPage />} />
            </Routes>
          </Layout>
        </DayDrawerProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
