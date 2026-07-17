import { createContext, useContext } from "react";
import { useLocation } from "react-router-dom";

const Ctx = createContext(false);

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const isDemo = pathname.startsWith("/demo");
  return <Ctx.Provider value={isDemo}>{children}</Ctx.Provider>;
}

export function useIsDemo() { return useContext(Ctx); }
