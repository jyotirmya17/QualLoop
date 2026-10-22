import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { PortfolioOverview } from './components/PortfolioOverview';
import { CampaignAdTable } from './components/CampaignAdTable';
import { AdDetailModal } from './components/AdDetailModal';
import { SimulationRunnerModal } from './components/SimulationRunnerModal';
import { BenchmarkView } from './components/BenchmarkView';
import { AuditTrailView } from './components/AuditTrailView';
import { HealthView } from './components/HealthView';
import { api } from './services/api';
import {
  SimulationRun,
  CampaignSummary,
  AdAnalysis,
  BenchmarkReport,
  HealthStatus,
  Decision,
} from './types/api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'portfolio' | 'benchmark' | 'audit' | 'health'>('portfolio');
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReport | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean>(true);

  // Modals & loading states
  const [isRunnerOpen, setIsRunnerOpen] = useState<boolean>(false);
  const [inspectedAd, setInspectedAd] = useState<AdAnalysis | null>(null);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState<boolean>(false);
  const [isLoadingBenchmark, setIsLoadingBenchmark] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // 1. Initial Load: Scenarios, Health, Recent Runs
  const initialize = useCallback(async () => {
    setIsRefreshing(true);
    try {
      // Health check
      try {
        const root = await api.getRoot();
        setHealthStatus(root);
        setIsBackendHealthy(true);
      } catch (err) {
        setIsBackendHealthy(false);
      }

      // Scenarios list
      try {
        const scResp = await api.listScenarios();
        setScenarios(scResp.scenarios);
      } catch (err) {
        console.error('Failed to fetch scenarios', err);
      }

      // Recent simulations
      const recentRuns = await api.listSimulations();
      if (recentRuns.length > 0) {
        setRuns(recentRuns);
        setSelectedRunId(recentRuns[0].id);
      } else {
        // Run default simulation if store is empty
        const defaultRun = await api.runSimulation('mixed_portfolio', 42);
        setRuns([defaultRun]);
        setSelectedRunId(defaultRun.id);
      }

      // Fetch benchmark report if exists
      try {
        const bench = await api.getLatestBenchmark();
        setBenchmarkReport(bench);
      } catch (err) {
        console.error('Failed to fetch benchmark', err);
      }

      // Fetch decisions & audit log
      try {
        const decs = await api.listDecisions();
        setDecisions(decs);
        const audits = await api.getAuditLog();
        setAuditEvents(audits);
      } catch (err) {
        console.error('Failed to fetch audit log', err);
      }
    } catch (err) {
      console.error('Initialization error:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  // 2. Fetch analysis when selected run changes
  useEffect(() => {
    if (!selectedRunId) return;

    let isCancelled = false;
    const fetchAnalysis = async () => {
      setIsLoadingAnalysis(true);
      try {
        const data = await api.getRunAnalysis(selectedRunId);
        if (!isCancelled) {
          setCampaigns(data);
        }
      } catch (err) {
        console.error(`Failed to load analysis for run ${selectedRunId}:`, err);
      } finally {
        if (!isCancelled) {
          setIsLoadingAnalysis(false);
        }
      }
    };

    fetchAnalysis();

    return () => {
      isCancelled = true;
    };
  }, [selectedRunId]);

  // Run new simulation handler
  const handleRunSimulation = async (scenario: string, seed: number) => {
    setIsRefreshing(true);
    try {
      const newRun = await api.runSimulation(scenario, seed);
      setRuns((prev) => [newRun, ...prev]);
      setSelectedRunId(newRun.id);
      // Refresh decisions & audit log
      const decs = await api.listDecisions();
      setDecisions(decs);
    } catch (err) {
      console.error('Error running simulation:', err);
      alert('Failed to run simulation. Please ensure backend is online.');
    } finally {
      setIsRefreshing(false);
    }
  };

  // Run benchmark handler
  const handleRunBenchmark = async (maxRuns: number) => {
    setIsLoadingBenchmark(true);
    try {
      const report = await api.runBenchmark(maxRuns);
      setBenchmarkReport(report);
    } catch (err) {
      console.error('Benchmark execution error:', err);
      alert('Failed to execute benchmark.');
    } finally {
      setIsLoadingBenchmark(false);
    }
  };

  const currentRun = runs.find((r) => r.id === selectedRunId);

  return (
    <div className="app-container">
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        runs={runs}
        selectedRunId={selectedRunId}
        onSelectRun={setSelectedRunId}
        onOpenRunner={() => setIsRunnerOpen(true)}
        isBackendHealthy={isBackendHealthy}
        isRefreshing={isRefreshing}
        onRefresh={initialize}
      />

      <main style={{ marginTop: '8px' }}>
        {activeTab === 'portfolio' && (
          <div className="animate-fade-in">
            <PortfolioOverview
              campaigns={campaigns}
              scenarioName={currentRun?.scenario_name}
              seed={currentRun?.seed}
            />

            {isLoadingAnalysis ? (
              <div className="glass-card" style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
                Computing Bayesian estimates and evaluating decision policies...
              </div>
            ) : (
              <CampaignAdTable
                campaigns={campaigns}
                onSelectAd={(ad) => setInspectedAd(ad)}
              />
            )}
          </div>
        )}

        {activeTab === 'benchmark' && (
          <div className="animate-fade-in">
            <BenchmarkView
              report={benchmarkReport}
              onRunBenchmark={handleRunBenchmark}
              isLoading={isLoadingBenchmark}
            />
          </div>
        )}

        {activeTab === 'audit' && (
          <div className="animate-fade-in">
            <AuditTrailView
              decisions={decisions}
              auditEvents={auditEvents}
              isLoading={isRefreshing}
            />
          </div>
        )}

        {activeTab === 'health' && (
          <div className="animate-fade-in">
            <HealthView
              health={healthStatus}
              isBackendHealthy={isBackendHealthy}
            />
          </div>
        )}
      </main>

      {/* Simulation Runner Modal */}
      <SimulationRunnerModal
        scenarios={scenarios}
        isOpen={isRunnerOpen}
        onClose={() => setIsRunnerOpen(false)}
        onRunSimulation={handleRunSimulation}
        isLoading={isRefreshing}
      />

      {/* Ad Inspector Modal */}
      <AdDetailModal
        adAnalysis={inspectedAd}
        onClose={() => setInspectedAd(null)}
      />
    </div>
  );
};
export default App;
