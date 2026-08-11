import { NavLink, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import Portfolio from "./pages/Portfolio";
import Market from "./pages/Market";
import Risk from "./pages/Risk";
import Chat from "./pages/Chat";

const navLinkClass = ({ isActive }: { isActive: boolean }): string =>
  isActive ? "font-semibold text-blue-600" : "text-gray-600 hover:text-blue-600";

function App(): JSX.Element {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="flex gap-6 border-b bg-white px-6 py-4 shadow-sm">
        <NavLink to="/" className="font-bold text-gray-900" end>
          Akıllı Kişisel Finans Danışmanı
        </NavLink>
        <NavLink to="/dashboard" className={navLinkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/portfolio" className={navLinkClass}>
          Portföy
        </NavLink>
        <NavLink to="/market" className={navLinkClass}>
          Piyasa
        </NavLink>
        <NavLink to="/risk" className={navLinkClass}>
          Risk
        </NavLink>
        <NavLink to="/chat" className={navLinkClass}>
          Chat
        </NavLink>
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/market" element={<Market />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/chat" element={<Chat />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
