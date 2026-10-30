"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, coll, proj } from "@/lib/api";
import type {
  Analytics,
  AnswerResult,
  ApiKey,
  ApiKeyCreated,
  AuditEvent,
  Chunk,
  ChunkStats,
  Collection,
  Comparison,
  Dataset,
  DatasetItem,
  Document,
  DocumentDetail,
  GateResult,
  GateSettings,
  IngestResult,
  Me,
  Member,
  Page,
  PipelineConfig,
  PipelineVersion,
  Preview,
  Project,
  QueryResult,
  Role,
  Run,
  RunResult,
  SystemInfo,
  User,
} from "@/lib/types";

export const qk = {
  system: ["system"] as const,
  me: ["me"] as const,
  project: (p: string) => ["project", p] as const,
  collections: (p: string) => ["collections", p] as const,
  collection: (p: string, c: string) => ["collection", p, c] as const,
  documents: (p: string, c: string) => ["documents", p, c] as const,
  document: (p: string, c: string, id: string) => ["document", p, c, id] as const,
  pipelines: (p: string, c: string) => ["pipelines", p, c] as const,
  chunks: (p: string, c: string, v: number) => ["chunks", p, c, v] as const,
  datasets: (p: string) => ["datasets", p] as const,
  dataset: (p: string, d: string) => ["dataset", p, d] as const,
  runs: (p: string) => ["runs", p] as const,
  run: (p: string, id: string) => ["run", p, id] as const,
  analytics: (p: string) => ["analytics", p] as const,
  members: (p: string) => ["members", p] as const,
  apiKeys: (p: string) => ["api-keys", p] as const,
  activity: (p: string) => ["activity", p] as const,
};

const BUSY = new Set(["queued", "processing", "running", "building"]);

// Accounts --------------------------------------------------------------------------------

export function useSystemInfo() {
  return useQuery({
    queryKey: qk.system,
    queryFn: () => api<SystemInfo>("/api/v1/system/info"),
    staleTime: 300_000,
  });
}

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api<Me>("/api/v1/auth/me"), retry: false });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<{ user: User }>("/api/v1/auth/login", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useSignup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; name: string; password: string }) =>
      api<{ user: User }>("/api/v1/auth/signup", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/api/v1/auth/logout", { method: "POST" }),
    onSettled: () => client.clear(),
  });
}

// Projects --------------------------------------------------------------------------------

export function useProject(project: string) {
  return useQuery({ queryKey: qk.project(project), queryFn: () => api<Project>(proj(project)) });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description: string }) =>
      api<Project>("/api/v1/projects", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useUpdateProject(project: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string }) =>
      api<Project>(proj(project), { method: "PATCH", json: body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.project(project) });
      client.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useMembers(project: string) {
  return useQuery({
    queryKey: qk.members(project),
    queryFn: () => api<Member[]>(`${proj(project)}/members`),
  });
}

export function useMemberActions(project: string) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: qk.members(project) });
  return {
    add: useMutation({
      mutationFn: (body: { email: string; name?: string; role: Role }) =>
        api<{ member: Member; temporary_password: string | null }>(`${proj(project)}/members`, {
          method: "POST",
          json: body,
        }),
      onSuccess: refresh,
    }),
    change: useMutation({
      mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
        api<Member>(`${proj(project)}/members/${userId}`, { method: "PATCH", json: { role } }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (userId: string) =>
        api<void>(`${proj(project)}/members/${userId}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useApiKeys(project: string) {
  return useQuery({
    queryKey: qk.apiKeys(project),
    queryFn: () => api<ApiKey[]>(`${proj(project)}/api-keys`),
  });
}

export function useApiKeyActions(project: string) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: qk.apiKeys(project) });
  return {
    create: useMutation({
      mutationFn: (body: {
        name: string;
        role: "viewer" | "editor";
        expires_in_days: number | null;
      }) => api<ApiKeyCreated>(`${proj(project)}/api-keys`, { method: "POST", json: body }),
      onSuccess: refresh,
    }),
    revoke: useMutation({
      mutationFn: (id: string) =>
        api<void>(`${proj(project)}/api-keys/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useActivity(project: string) {
  return useQuery({
    queryKey: qk.activity(project),
    queryFn: () => api<Page<AuditEvent>>(`${proj(project)}/activity?limit=50`),
  });
}

// Collections and documents ---------------------------------------------------------------

export function useCollections(project: string) {
  return useQuery({
    queryKey: qk.collections(project),
    queryFn: () => api<Collection[]>(`${proj(project)}/collections`),
  });
}

export function useCollection(project: string, collection: string) {
  return useQuery({
    queryKey: qk.collection(project, collection),
    queryFn: () => api<Collection>(coll(project, collection)),
  });
}

export function useCreateCollection(project: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description: string; pipeline: PipelineConfig }) =>
      api<Collection>(`${proj(project)}/collections`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.collections(project) }),
  });
}

export type DocumentFilters = { status?: string; q?: string };

export function useDocuments(project: string, collection: string, filters: DocumentFilters = {}) {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.status) params.set("status", filters.status);
  if (filters.q) params.set("q", filters.q);
  return useQuery({
    queryKey: [...qk.documents(project, collection), filters],
    queryFn: () => api<Page<Document>>(`${coll(project, collection)}/documents?${params}`),
    placeholderData: keepPreviousData,
    // Follow ingestion while anything is still being parsed.
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => BUSY.has(d.status)) ? 2000 : false,
  });
}

export function useDocument(project: string, collection: string, id: string) {
  return useQuery({
    queryKey: qk.document(project, collection, id),
    queryFn: () => api<DocumentDetail>(`${coll(project, collection)}/documents/${id}`),
    refetchInterval: (query) => {
      const detail = query.state.data;
      return detail && (BUSY.has(detail.status) || detail.indexes.some((i) => BUSY.has(i.status)))
        ? 2000
        : false;
    },
  });
}

export function useIngest(project: string, collection: string) {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: qk.documents(project, collection) });
    client.invalidateQueries({ queryKey: qk.collection(project, collection) });
    client.invalidateQueries({ queryKey: qk.pipelines(project, collection) });
  };
  return {
    upload: useMutation({
      mutationFn: ({ files, metadata }: { files: File[]; metadata: Record<string, unknown> }) => {
        const form = new FormData();
        for (const file of files) form.append("files", file);
        if (Object.keys(metadata).length) form.append("metadata", JSON.stringify(metadata));
        return api<IngestResult>(`${coll(project, collection)}/documents`, {
          method: "POST",
          body: form,
        });
      },
      onSuccess: refresh,
    }),
    importSources: useMutation({
      mutationFn: (items: Record<string, unknown>[]) =>
        api<IngestResult>(`${coll(project, collection)}/documents/import`, {
          method: "POST",
          json: { items },
        }),
      onSuccess: refresh,
    }),
  };
}

export function useDocumentActions(project: string, collection: string) {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: qk.documents(project, collection) });
    client.invalidateQueries({ queryKey: ["document", project, collection] });
    client.invalidateQueries({ queryKey: qk.pipelines(project, collection) });
  };
  return {
    reprocess: useMutation({
      mutationFn: (id: string) =>
        api<Document>(`${coll(project, collection)}/documents/${id}/reprocess`, { method: "POST" }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api<void>(`${coll(project, collection)}/documents/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

// Pipelines -------------------------------------------------------------------------------

export function usePipelines(project: string, collection: string, enabled = true) {
  return useQuery({
    queryKey: qk.pipelines(project, collection),
    queryFn: () => api<PipelineVersion[]>(`${coll(project, collection)}/pipelines`),
    enabled: enabled && Boolean(collection),
    refetchInterval: (query) =>
      query.state.data?.some((v) => BUSY.has(v.index.status)) ? 2000 : false,
  });
}

export function useCreatePipeline(project: string, collection: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name: string;
      description: string;
      config: PipelineConfig;
      activate: boolean;
    }) =>
      api<PipelineVersion>(`${coll(project, collection)}/pipelines`, {
        method: "POST",
        json: body,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.pipelines(project, collection) });
      client.invalidateQueries({ queryKey: qk.collection(project, collection) });
      client.invalidateQueries({ queryKey: qk.collections(project) });
    },
  });
}

export function useActivate(project: string, collection: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (version: number) =>
      api<PipelineVersion>(`${coll(project, collection)}/pipelines/${version}/activate`, {
        method: "POST",
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.pipelines(project, collection) });
      client.invalidateQueries({ queryKey: qk.collection(project, collection) });
      client.invalidateQueries({ queryKey: qk.collections(project) });
    },
  });
}

export function useChunks(
  project: string,
  collection: string,
  version: number,
  { documentId, offset }: { documentId?: string; offset: number },
) {
  const params = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (documentId) params.set("document_id", documentId);
  return useQuery({
    queryKey: [...qk.chunks(project, collection, version), documentId ?? "", offset],
    queryFn: () =>
      api<Page<Chunk>>(`${coll(project, collection)}/pipelines/${version}/chunks?${params}`),
    placeholderData: keepPreviousData,
  });
}

export function useChunkStats(project: string, collection: string, version: number) {
  return useQuery({
    queryKey: [...qk.chunks(project, collection, version), "stats"],
    queryFn: () =>
      api<ChunkStats>(`${coll(project, collection)}/pipelines/${version}/chunks/stats`),
  });
}

export function usePreview(project: string, collection: string) {
  return useMutation({
    mutationFn: (body: {
      cleaning: PipelineConfig["cleaning"];
      chunking: PipelineConfig["chunking"];
      document_id?: string;
      text?: string;
    }) =>
      api<Preview>(`${coll(project, collection)}/pipelines/preview`, {
        method: "POST",
        json: body,
      }),
  });
}

// Serving ---------------------------------------------------------------------------------

export type PlaygroundRequest = {
  collection: string;
  answer: boolean;
  body: Record<string, unknown>;
};

export type PlaygroundResult = { retrieval: QueryResult; answer: AnswerResult | null };

/**
 * One side of the playground. A query, not a mutation, so the URL is the state: reloading,
 * sharing a link or going back shows the same request. Results never go stale on their own
 * (every run is logged as traffic), and a failed request is not retried.
 */
export function usePlaygroundRun(project: string, request: PlaygroundRequest | null) {
  return useQuery({
    queryKey: ["playground", project, request],
    queryFn: async (): Promise<PlaygroundResult> => {
      const { collection, answer, body } = request as PlaygroundRequest;
      if (answer) {
        const result = await api<AnswerResult>(`${coll(project, collection)}/answer`, {
          method: "POST",
          json: body,
        });
        return { retrieval: result.retrieval, answer: result };
      }
      const retrieval = await api<QueryResult>(`${coll(project, collection)}/query`, {
        method: "POST",
        json: body,
      });
      return { retrieval, answer: null };
    },
    enabled: request !== null,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
}

export function useAnalytics(project: string, days: number, collection?: string, enabled = true) {
  const params = new URLSearchParams({ days: String(days) });
  if (collection) params.set("collection", collection);
  return useQuery({
    queryKey: [...qk.analytics(project), days, collection ?? ""],
    queryFn: () => api<Analytics>(`${proj(project)}/analytics?${params}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}

// Evaluation ------------------------------------------------------------------------------

export function useDatasets(project: string) {
  return useQuery({
    queryKey: qk.datasets(project),
    queryFn: () => api<Dataset[]>(`${proj(project)}/datasets`),
  });
}

export function useDataset(project: string, dataset: string) {
  return useQuery({
    queryKey: qk.dataset(project, dataset),
    queryFn: () => api<Dataset>(`${proj(project)}/datasets/${encodeURIComponent(dataset)}`),
    enabled: Boolean(dataset),
  });
}

export function useDatasetItems(project: string, dataset: string) {
  return useQuery({
    queryKey: [...qk.dataset(project, dataset), "items"],
    queryFn: () =>
      api<Page<DatasetItem>>(
        `${proj(project)}/datasets/${encodeURIComponent(dataset)}/items?limit=500`,
      ),
  });
}

export function useDatasetActions(project: string) {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: qk.datasets(project) });
    client.invalidateQueries({ queryKey: ["dataset", project] });
  };
  return {
    create: useMutation({
      mutationFn: (body: {
        name: string;
        collection: string;
        description: string;
        items: unknown[];
      }) => api<Dataset>(`${proj(project)}/datasets`, { method: "POST", json: body }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({
        slug,
        body,
      }: {
        slug: string;
        body: { name?: string; description?: string; gate?: GateSettings };
      }) =>
        api<Dataset>(`${proj(project)}/datasets/${encodeURIComponent(slug)}`, {
          method: "PATCH",
          json: body,
        }),
      onSuccess: refresh,
    }),
    importItems: useMutation({
      mutationFn: ({
        slug,
        items,
        replace,
      }: {
        slug: string;
        items: unknown[];
        replace: boolean;
      }) =>
        api<Dataset>(`${proj(project)}/datasets/${encodeURIComponent(slug)}/items`, {
          method: "POST",
          json: { items, replace },
        }),
      onSuccess: refresh,
    }),
  };
}

export function useRuns(project: string, dataset?: string) {
  const params = new URLSearchParams({ limit: "100" });
  if (dataset) params.set("dataset", dataset);
  return useQuery({
    queryKey: [...qk.runs(project), dataset ?? ""],
    queryFn: () => api<Page<Run>>(`${proj(project)}/eval-runs?${params}`),
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => BUSY.has(r.status)) ? 2000 : false,
  });
}

export function useRun(project: string, id: string) {
  return useQuery({
    queryKey: qk.run(project, id),
    queryFn: () => api<Run>(`${proj(project)}/eval-runs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data && BUSY.has(query.state.data.status) ? 1500 : false,
  });
}

export function useRunResults(project: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...qk.run(project, id), "results"],
    queryFn: () => api<Page<RunResult>>(`${proj(project)}/eval-runs/${id}/results?limit=500`),
    enabled,
  });
}

export function useRunActions(project: string) {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: qk.runs(project) });
    client.invalidateQueries({ queryKey: ["run", project] });
    client.invalidateQueries({ queryKey: qk.datasets(project) });
    client.invalidateQueries({ queryKey: ["dataset", project] });
  };
  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) =>
        api<Run>(`${proj(project)}/eval-runs`, { method: "POST", json: body }),
      onSuccess: refresh,
    }),
    baseline: useMutation({
      mutationFn: (id: string) =>
        api<Run>(`${proj(project)}/eval-runs/${id}/baseline`, { method: "POST" }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        api<void>(`${proj(project)}/eval-runs/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useComparison(project: string, ids: string[]) {
  return useQuery({
    queryKey: ["compare", project, ids.join(",")],
    queryFn: () => api<Comparison>(`${proj(project)}/eval-runs/compare?ids=${ids.join(",")}`),
    enabled: ids.length >= 2,
  });
}

export function useGate(project: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...qk.run(project, id), "gate"],
    queryFn: () =>
      api<GateResult>(`${proj(project)}/eval-runs/${id}/gate`, { method: "POST", json: {} }),
    enabled,
  });
}
