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

export type SignalItem = {
  signal_id: string;
  title: string;
  source: string;
  region?: string | null;
  severity_hint?: string | null;
};

export type SignalResponse = {
  signals: SignalItem[];
};

export type RunItem = {
  run_id: string;
  created_at: string;
  scenario_name?: string | null;
  route?: string | null;
  max_severity?: number | null;
};

export type RunListResponse = {
  runs: RunItem[];
};

export type RunRequest = {
  scenario_name: string | null;
  use_pending_signals: boolean;
};
