import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "./client";
import type {
  Approval,
  CollectResult,
  ConfigSnapshot,
  DisruptionSignal,
  HealthResponse,
  PipelineState,
  RecentRun,
  Simulation,
  SupplyNetwork,
  WhatIfRequest,
} from "../types/state";

export interface RunArgs {
  scenario_name: string | null;
  use_pending_signals: boolean;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => (await client.get<HealthResponse>("/health")).data,
    refetchInterval: 30000,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: async () =>
      (await client.get<{ scenarios: string[] }>("/scenarios")).data.scenarios,
    staleTime: 5 * 60 * 1000,
  });
}

export function useNetwork() {
  return useQuery({
    queryKey: ["network"],
    queryFn: async () => (await client.get<SupplyNetwork>("/network")).data,
    staleTime: 10 * 60 * 1000,
  });
}

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: ["runs", limit],
    queryFn: async () =>
      (await client.get<{ runs: RecentRun[] }>("/runs", { params: { limit } }))
        .data.runs,
  });
}

export function useSignals(limit = 50) {
  return useQuery({
    queryKey: ["signals", limit],
    queryFn: async () =>
      (
        await client.get<{ signals: DisruptionSignal[] }>("/signals", {
          params: { limit },
        })
      ).data.signals,
  });
}

export function useRunPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: RunArgs) =>
      (await client.post<PipelineState>("/run", args)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["signals"] });
    },
  });
}

export function useWhatIf() {
  return useMutation({
    mutationFn: async (args: WhatIfRequest) =>
      (await client.post<Simulation>("/what-if", args)).data,
  });
}

export function useApprovals(runId: string | undefined) {
  return useQuery({
    queryKey: ["approvals", runId],
    queryFn: async () =>
      (
        await client.get<{ approvals: Approval[] }>("/approvals", {
          params: { run_id: runId },
        })
      ).data.approvals,
    enabled: Boolean(runId),
  });
}

export function useApproveAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: Approval) =>
      (await client.post<Approval>("/approvals", args)).data,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["approvals", variables.run_id] });
    },
  });
}

export function useCollect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await client.post<CollectResult>("/collect")).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signals"] });
    },
  });
}

export function useAsk() {
  return useMutation({
    mutationFn: async (question: string) =>
      (await client.post<{ answer: string }>("/ask", { question })).data.answer,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: async () => (await client.get<ConfigSnapshot>("/config")).data,
    enabled: false,
  });
}

export function useSaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      (await client.post<ConfigSnapshot>("/config", { values })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });
}
