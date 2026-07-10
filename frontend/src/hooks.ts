import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export function useProject(prof: string, slug: string) {
  return useQuery({
    queryKey: ["project", prof, slug],
    queryFn: () => api.project(prof, slug),
    refetchInterval: (query) =>
      query.state.data?.job?.status === "running" ? 2000 : false,
  });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: Infinity });
}

export function useInvalidateProject(prof: string, slug: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["project", prof, slug] });
}
