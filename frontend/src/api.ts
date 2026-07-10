const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'API request failed');
  }

  return response.json();
}

export function getHealth() {
  return request<HealthResponse>('/health');
}

export function runPipeline(payload: RunRequest) {
  return request<RunResponse>('/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSignals() {
  return request<SignalResponse>('/signals');
}

export function getRuns() {
  return request<RunListResponse>('/runs');
}

export type RunRequest = {
  scenario_name: string | null;
  use_pending_signals: boolean;
};

export type HealthResponse = {
  status: string;
  database: string;
  database_mode: string;
  llm_mode: string;
  data_dir: string;
  retrieval_mode: string;
  retriever_stats: Record<string, unknown>;
};

export type RunResponse = Record<string, unknown>;

export type SignalResponse = {
  signals: Array<{
    signal_id: string;
    title: string;
    source: string;
    region?: string | null;
    severity_hint?: string | null;
  }>;
};

export type RunListResponse = {
  runs: Array<{
    run_id: string;
    created_at: string;
    scenario_name?: string | null;
    route?: string | null;
    max_severity?: number | null;
  }>;
};
