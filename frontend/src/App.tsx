import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { Toaster } from "./components/toast";
import HistoryView from "./pages/HistoryView";
import ProjectBoard from "./pages/ProjectBoard";
import ProjectList from "./pages/ProjectList";
import TakeCompare from "./pages/TakeCompare";

function TopBar() {
  const { slug } = useParams();
  return (
    <header className="topbar">
      <NavLink className="mark" to="/">
        Scene<span>Forge</span> Studio
      </NavLink>
      {slug && (
        <nav>
          <NavLink to={`/p/${slug}`} end>
            Board
          </NavLink>
          <NavLink to={`/p/${slug}/history`}>History</NavLink>
        </nav>
      )}
    </header>
  );
}

function WithBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <TopBar />
      {children}
      <Toaster />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WithBar><ProjectList /></WithBar>} />
      <Route path="/p/:slug" element={<WithBar><ProjectBoard /></WithBar>} />
      <Route path="/p/:slug/scenes/:sid/takes" element={<WithBar><TakeCompare /></WithBar>} />
      <Route path="/p/:slug/history" element={<WithBar><HistoryView /></WithBar>} />
    </Routes>
  );
}
