import { useQuery, useQueryClient } from "@tanstack/react-query";
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
