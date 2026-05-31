import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import StatusBar from "./components/StatusBar";
import ModeBanner from "@/components/ui/ModeBanner";
import { NAV_ITEMS } from "./routes";
import StrategyDetailPage from "./pages/Strategies/Detail";
import Credentials from "./pages/Settings/Credentials";

export default function App() {
  return (
    <div className="flex flex-col h-screen bg-neutral-950 text-neutral-100">
      <ModeBanner />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              {NAV_ITEMS.map((item) => (
                <Route key={item.path} path={item.path} element={item.element} />
              ))}
              <Route path="/strategies/:id" element={<StrategyDetailPage />} />
              <Route path="/settings/credentials" element={<Credentials />} />
            </Routes>
          </main>
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
