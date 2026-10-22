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

  // Ads & Campaign Analysis
  getRunAnalysis: (runId: string) => fetchJson<CampaignSummary[]>(`/ads/run/${runId}`),

  // Decisions & Audit
  listDecisions: () => fetchJson<Decision[]>('/decisions/'),
  getAuditLog: () => fetchJson<any[]>('/audit/'),

  // Benchmark
  getLatestBenchmark: () => fetchJson<BenchmarkReport>('/benchmark/latest'),
  runBenchmark: (maxRunsPerScenario: number = 5) =>
    fetchJson<BenchmarkReport>('/benchmark/run', {
      method: 'POST',
      body: JSON.stringify({ max_runs_per_scenario: maxRunsPerScenario }),
    }),
};
