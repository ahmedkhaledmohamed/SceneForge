import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { Toaster } from "./components/toast";
import HistoryView from "./pages/HistoryView";
import ProfileList from "./pages/ProfileList";
import ProjectBoard from "./pages/ProjectBoard";
import ProjectList from "./pages/ProjectList";
import Settings from "./pages/Settings";
import TakeCompare from "./pages/TakeCompare";

function TopBar() {
  const { prof, slug } = useParams();
  return (
    <header className="topbar">
      <NavLink className="mark" to="/">
        Scene<span>Forge</span> Studio
      </NavLink>
      <nav>
        {prof && (
          <>
            <NavLink to={`/${prof}`} end>
              {prof}
            </NavLink>
            <NavLink to={`/${prof}/settings`}>
              settings
            </NavLink>
          </>
        )}
        {prof && slug && (
          <>
            <NavLink to={`/${prof}/p/${slug}`} end>
              Board
            </NavLink>
            <NavLink to={`/${prof}/p/${slug}/history`}>History</NavLink>
          </>
        )}
      </nav>
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
      <Route path="/" element={<WithBar><ProfileList /></WithBar>} />
      <Route path="/:prof" element={<WithBar><ProjectList /></WithBar>} />
      <Route path="/:prof/settings" element={<WithBar><Settings /></WithBar>} />
      <Route path="/:prof/p/:slug" element={<WithBar><ProjectBoard /></WithBar>} />
      <Route path="/:prof/p/:slug/scenes/:sid/takes" element={<WithBar><TakeCompare /></WithBar>} />
      <Route path="/:prof/p/:slug/history" element={<WithBar><HistoryView /></WithBar>} />
    </Routes>
  );
}
