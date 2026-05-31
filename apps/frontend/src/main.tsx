import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import LoginPage from "./pages/Login";
import { RequireAuth } from "./components/auth/RequireAuth";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* P5 §3: /login is public; everything else requires a session. */}
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/*"
            element={
              <RequireAuth>
                <App />
              </RequireAuth>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
