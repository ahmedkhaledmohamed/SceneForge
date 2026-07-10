import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const Ctx = createContext(false);

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    api.models().then(() => setDemo(false)).catch(() => setDemo(true));
  }, []);

  return <Ctx.Provider value={demo}>{children}</Ctx.Provider>;
}

export function useIsDemo() { return useContext(Ctx); }
