import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Project doc, refreshed every 2s while a job runs (the polling story). */
export function useProject(slug: string) {
  return useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.project(slug),
    refetchInterval: (query) =>
      query.state.data?.job?.status === "running" ? 2000 : false,
  });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: Infinity });
}

export function useInvalidateProject(slug: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["project", slug] });
}
