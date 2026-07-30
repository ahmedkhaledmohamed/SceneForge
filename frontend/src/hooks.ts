import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "./api";
import { DEMO_MODELS } from "./demo";
import { useIsDemo } from "./DemoContext";

export function useProject(prof: string, slug: string) {
  const isDemo = useIsDemo();
  return useQuery({
    queryKey: ["project", prof, slug],
    queryFn: () => api.project(prof, slug),
    enabled: !isDemo,
    refetchInterval: (query) =>
      query.state.data?.job?.status === "running" ? 2000 : false,
    staleTime: 5000,
  });
}

export function useModels() {
  const isDemo = useIsDemo();
  return useQuery({
    queryKey: ["models"],
    queryFn: () => (isDemo ? Promise.resolve(DEMO_MODELS) : api.models()),
    staleTime: Infinity,
  });
}

export function useInvalidateProject(prof: string, slug: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["project", prof, slug] });
}

export function useInvalidateProfileStats(prof: string) {
  const client = useQueryClient();
  return () => {
    client.invalidateQueries({ queryKey: ["stats", prof] });
    client.invalidateQueries({ queryKey: ["analytics", prof] });
  };
}

export function useProfileScope(prof: string) {
  const client = useQueryClient();
  const prevProf = useRef(prof);

  useEffect(() => {
    if (prevProf.current && prevProf.current !== prof) {
      const old = prevProf.current;
      client.removeQueries({ queryKey: ["project", old] });
      client.removeQueries({ queryKey: ["projects", old] });
      client.removeQueries({ queryKey: ["profile", old] });
      client.removeQueries({ queryKey: ["stats", old] });
      client.removeQueries({ queryKey: ["analytics", old] });
      client.removeQueries({ queryKey: ["settings", old] });
      client.removeQueries({ queryKey: ["balance", old] });
      client.removeQueries({ queryKey: ["templates", old] });
      client.removeQueries({ queryKey: ["assets", old] });
      client.removeQueries({ queryKey: ["prompts", old] });
      client.removeQueries({ queryKey: ["sequence", old] });
    }
    prevProf.current = prof;
  }, [prof, client]);
}
