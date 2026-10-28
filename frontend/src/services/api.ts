import {
  SimulationRun,
  CampaignSummary,
  BenchmarkReport,
  HealthStatus,
  Decision,
} from '../types/api';

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error ${response.status}: ${errorText || response.statusText}`);
  }

  return response.json();
}

export const api = {
  // Health
  getHealth: () => fetchJson<HealthStatus>('/health'),
  getRoot: () => fetchJson<HealthStatus>('/'),

  // Simulations
  listSimulations: () => fetchJson<SimulationRun[]>('/simulations/'),
  getSimulation: (id: string) => fetchJson<SimulationRun>(`/simulations/${id}`),
  listScenarios: () => fetchJson<{ scenarios: string[] }>('/simulations/scenarios'),
  runSimulation: (scenario_name: string, seed: number) =>
    fetchJson<SimulationRun>('/simulations/run', {
      method: 'POST',
      body: JSON.stringify({ scenario_name, seed }),
    }),
  evaluateSimulation: (runId: string) =>
    fetchJson<CampaignSummary[]>(`/simulations/${runId}/evaluate`, {
      method: 'POST',
    }),

  // Ads & Campaign Analysis
  getRunAnalysis: (runId: string) => fetchJson<CampaignSummary[]>(`/ads/run/${runId}`),

  // Decisions & Audit
  listDecisions: (params?: { simulation_run_id?: string; advertisement_id?: string; action?: string; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.simulation_run_id) searchParams.set('simulation_run_id', params.simulation_run_id);
    if (params?.advertisement_id) searchParams.set('advertisement_id', params.advertisement_id);
    if (params?.action) searchParams.set('action', params.action);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    const query = searchParams.toString();
    return fetchJson<Decision[]>(`/decisions/${query ? `?${query}` : ''}`);
  },
  getAuditLog: (params?: { decision_id?: string; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.decision_id) searchParams.set('decision_id', params.decision_id);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    const query = searchParams.toString();
    return fetchJson<any[]>(`/audit/${query ? `?${query}` : ''}`);
  },

  // Benchmark
  getLatestBenchmark: () => fetchJson<BenchmarkReport>('/benchmark/latest'),
  runBenchmark: (maxRunsPerScenario: number = 5) =>
    fetchJson<BenchmarkReport>('/benchmark/run', {
      method: 'POST',
      body: JSON.stringify({ max_runs_per_scenario: maxRunsPerScenario }),
    }),
};
