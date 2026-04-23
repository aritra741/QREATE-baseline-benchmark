"use client";

import { useState, useEffect } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { ControlPanel } from "@/components/dashboard/ControlPanel";
import { SystemColumn } from "@/components/dashboard/SystemColumn";
import { MetricsDashboard } from "@/components/dashboard/MetricsDashboard";
import { System, SystemMetrics, QueryResult } from "@/types";
import workloadData from "@/data/dummyWorkload.json";

// ── static mock data ────────────────────────────────────────────────────────

const MOCK_METRICS: Record<string, SystemMetrics> = {
  ours: {
    preprocessingTime: "1 hour 8 minutes",
    runtime: 4.1, tokensUsed: 11190,
    precision: 0.65, recall: 0.62, f1: 0.63,
    matchingRows: 13, rowsInSystemNotGT: 7, rowsInGTNotSystem: 8,
  },
  squid: {
    preprocessingTime: "2 hours 13 minutes",
    runtime: 0.05, tokensUsed: 0,
    precision: 0.05, recall: 0.05, f1: 0.05,
    matchingRows: 1, rowsInSystemNotGT: 20, rowsInGTNotSystem: 20,
  },
  redd: {
    preprocessingTime: "No Preprocessing Needed",
    runtime: 3097, tokensUsed: 7524435,
    precision: 0.75, recall: 0.14, f1: 0.24,
    matchingRows: 3, rowsInSystemNotGT: 1, rowsInGTNotSystem: 18,
  },
  docetl: {
    preprocessingTime: "No Preprocessing Needed",
    runtime: 250, tokensUsed: 862000,
    precision: 0.60, recall: 0.55, f1: 0.57,
    matchingRows: 10, rowsInSystemNotGT: 5, rowsInGTNotSystem: 6,
  },
  quest: {
    preprocessingTime: "30 minutes",
    runtime: 2.5, tokensUsed: 3500,
    precision: 0.50, recall: 0.45, f1: 0.47,
    matchingRows: 8, rowsInSystemNotGT: 6, rowsInGTNotSystem: 9,
  },
  palimpzest: {
    preprocessingTime: "45 minutes",
    runtime: 180, tokensUsed: 450000,
    precision: 0.55, recall: 0.50, f1: 0.52,
    matchingRows: 9, rowsInSystemNotGT: 5, rowsInGTNotSystem: 8,
  },
};

const MOCK_RESULTS: Record<string, any[]> = {
  ours: [
    { team_name: "Chicago Bulls",    location: "Chicago",     player_count: 3,  __comparisonStatus: "match" },
    { team_name: "Boston Celtics",   location: "Boston",      player_count: 7,  __comparisonStatus: "match" },
    { team_name: "Dallas Mavericks", location: "Dallas",      player_count: 1,  __comparisonStatus: "extra" },
  ],
  squid: [
    { team_name: "Chicago Bulls",    location: "Chicago",     player_count: 14, __comparisonStatus: "extra" },
    { team_name: "Boston Celtics",   location: "Boston",      player_count: 84, __comparisonStatus: "extra" },
    { team_name: "Dallas Mavericks", location: "Dallas",      player_count: 28, __comparisonStatus: "extra" },
  ],
  redd: [
    { team_name: "Los Angeles Lakers", location: "Los Angeles", player_count: 7, __comparisonStatus: "match" },
    { team_name: "Boston Celtics",     location: "Boston",      player_count: 7, __comparisonStatus: "match" },
    { team_name: "Dallas Mavericks",   location: "Dallas",      player_count: 1, __comparisonStatus: "extra" },
  ],
  docetl: [
    { team_name: "Chicago Bulls",    location: "Chicago",     player_count: 3,  __comparisonStatus: "match" },
    { team_name: "Boston Celtics",   location: "Boston",      player_count: 7,  __comparisonStatus: "match" },
    { team_name: "Dallas Mavericks", location: "Dallas",      player_count: 2,  __comparisonStatus: "extra" },
  ],
  quest: [
    { team_name: "Chicago Bulls",    location: "Chicago",     player_count: 3,  __comparisonStatus: "match" },
    { team_name: "Boston Celtics",   location: "Boston",      player_count: 6,  __comparisonStatus: "extra" },
  ],
  palimpzest: [
    { team_name: "Chicago Bulls",    location: "Chicago",     player_count: 3,  __comparisonStatus: "match" },
    { team_name: "Boston Celtics",   location: "Boston",      player_count: 7,  __comparisonStatus: "match" },
    { team_name: "Los Angeles Lakers", location: "Los Angeles", player_count: 5, __comparisonStatus: "extra" },
  ],
};

// systems that show spinner for 10s on first reveal
const SLOW_SYSTEMS = new Set(["redd", "docetl"]);

export default function Home() {
  const [dataset,           setDataset]           = useState("");
  const [workload,          setWorkload]           = useState("");
  const [baselines,         setBaselines]          = useState<string[]>([]);
  const [currentQueryId,    setCurrentQueryId]     = useState("Q1");
  const [customQuery,       setCustomQuery]        = useState("");
  const [entityResolution,  setEntityResolution]   = useState("blink");
  const [llm,               setLlm]                = useState("qwen2.5-7b");
  const [activeMetric,      setActiveMetric]       = useState<"precision"|"recall"|"f1"|"runtime">("f1");

  // which system ids are fully visible (data ready)
  const [visibleSystems,  setVisibleSystems]  = useState<Set<string>>(new Set());
  // which system ids are currently in the loading spinner state
  const [loadingSystems,  setLoadingSystems]  = useState<Set<string>>(new Set());
  // queries that have actually been run (for the historical chart)
  const [executedQueries, setExecutedQueries] = useState<string[]>([]);

  const canRun = dataset !== "" && workload !== "";

  // When a new baseline is added, immediately show it (or spin if slow)
  useEffect(() => {
    baselines.forEach((b) => {
      if (!visibleSystems.has(b) && !loadingSystems.has(b)) {
        if (SLOW_SYSTEMS.has(b)) {
          setLoadingSystems((prev) => new Set([...prev, b]));
          setTimeout(() => {
            setLoadingSystems((prev) => { const n = new Set(prev); n.delete(b); return n; });
            setVisibleSystems((prev) => new Set([...prev, b]));
          }, 10000);
        } else {
          setVisibleSystems((prev) => new Set([...prev, b]));
        }
      }
    });
    // if a baseline was removed, clean up
    setVisibleSystems((prev) => {
      const n = new Set(prev);
      [...prev].forEach((id) => { if (id !== "ours" && !baselines.includes(id)) n.delete(id); });
      return n;
    });
    setLoadingSystems((prev) => {
      const n = new Set(prev);
      [...prev].forEach((id) => { if (!baselines.includes(id)) n.delete(id); });
      return n;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baselines]);

  function handleRunQuWARTS() {
    if (!canRun) return;
    setVisibleSystems(new Set(["ours"]));
    setLoadingSystems(new Set());
    // Record this query in history if not already there
    setExecutedQueries((prev) =>
      prev.includes(currentQueryId) ? prev : [...prev, currentQueryId]
    );
  }

  function handleAddBaseline(b: string) {
    setBaselines((prev) => [...prev, b]);
  }

  function handleRemoveBaseline(b: string) {
    setBaselines((prev) => prev.filter((x) => x !== b));
  }

  // Build the ordered list of systems to render
  const allSystemDefs: System[] = [
    { id: "ours",       name: "QuWARTS (Ours)", color: "#10b981" },
    { id: "squid",      name: "SQUiD",          color: "#3b82f6" },
    { id: "redd",       name: "ReDD",           color: "#94a3b8" },
    { id: "docetl",     name: "DocETL",         color: "#f59e0b" },
    { id: "quest",      name: "QUEST",          color: "#8b5cf6" },
    { id: "palimpzest", name: "Palimpzest",     color: "#ec4899" },
  ];

  const activeSystemIds = ["ours", ...baselines];
  const activeSystems = allSystemDefs.filter((s) => activeSystemIds.includes(s.id));
  const renderedSystems = activeSystems.filter(
    (s) => visibleSystems.has(s.id) || loadingSystems.has(s.id)
  );

  // History only includes metrics for systems that are fully visible,
  // and only for queries that have actually been run
  const mockHistory: QueryResult[] = workloadData
    .filter((q) => executedQueries.includes(q.id.toUpperCase()))
    .map((q) => {
      const idx = executedQueries.indexOf(q.id.toUpperCase());
    const allMetrics: Record<string, SystemMetrics> = {
      ours:   { f1: 0.63 - idx*0.02, precision: 0.65 - idx*0.01, recall: 0.62 - idx*0.02, runtime: 4.1  + idx*0.5, tokensUsed: 11190,   preprocessingTime: "", matchingRows: 0, rowsInSystemNotGT: 0, rowsInGTNotSystem: 0 },
      squid:  { f1: 0.05,            precision: 0.05,             recall: 0.05,            runtime: 0.05,           tokensUsed: 0,        preprocessingTime: "", matchingRows: 0, rowsInSystemNotGT: 0, rowsInGTNotSystem: 0 },
      redd:   { f1: 0.24 - idx*0.01, precision: 0.75 - idx*0.02, recall: 0.14 - idx*0.01, runtime: 3097,           tokensUsed: 7524435,  preprocessingTime: "", matchingRows: 0, rowsInSystemNotGT: 0, rowsInGTNotSystem: 0 },
      docetl: { f1: 0.57 - idx*0.01, precision: 0.60 - idx*0.01, recall: 0.55 - idx*0.01, runtime: 250,            tokensUsed: 862000,   preprocessingTime: "", matchingRows: 0, rowsInSystemNotGT: 0, rowsInGTNotSystem: 0 },
    };
    const filteredMetrics: Record<string, SystemMetrics> = {};
    visibleSystems.forEach((id) => {
      if (allMetrics[id]) filteredMetrics[id] = allMetrics[id];
    });
    return { queryId: q.id.toUpperCase(), metrics: filteredMetrics, results: {} };
  });

  return (
    <main className="h-screen flex flex-col bg-slate-50 text-slate-900 overflow-hidden font-sans">
      <TopBar
        dataset={dataset}
        workload={workload}
        baselines={baselines}
        onDatasetChange={setDataset}
        onWorkloadChange={setWorkload}
        onAddBaseline={handleAddBaseline}
        onRemoveBaseline={handleRemoveBaseline}
      />

      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-[350px] border-r border-slate-200 flex flex-col bg-white shrink-0">
          <ControlPanel
            currentQueryId={currentQueryId}
            onQuerySelect={setCurrentQueryId}
            customQuery={customQuery}
            onCustomQueryChange={setCustomQuery}
            entityResolution={entityResolution}
            onEntityResolutionChange={setEntityResolution}
            llm={llm}
            onLlmChange={setLlm}
            workloadSelected={workload !== ""}
          />
        </div>

        {/* Main area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {renderedSystems.length === 0 ? (
            /* Empty state — centered Run button */
            <div className="flex-1 flex flex-col items-center justify-center gap-4">
              <p className="text-sm text-slate-400 font-medium">
                {canRun
                  ? "Ready to run. Click below to execute QuWARTS."
                  : "Select a dataset and workload to get started."}
              </p>
              <button
                onClick={handleRunQuWARTS}
                disabled={!canRun}
                className={`px-6 py-3 rounded-xl font-black text-sm uppercase tracking-widest transition-all shadow-lg ${
                  canRun
                    ? "bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-600/30 active:scale-95"
                    : "bg-slate-200 text-slate-400 cursor-not-allowed shadow-none"
                }`}
              >
                Run QuWARTS
              </button>
            </div>
          ) : (
            <div className="flex-1 flex overflow-hidden">
              {/* System columns */}
              <div className="flex-1 flex overflow-x-auto">
                {renderedSystems.map((system) => (
                  <SystemColumn
                    key={system.id}
                    system={system}
                    metrics={visibleSystems.has(system.id) ? MOCK_METRICS[system.id] : undefined}
                    results={visibleSystems.has(system.id) ? MOCK_RESULTS[system.id] : undefined}
                    gtResults={MOCK_RESULTS["ours"]}
                    loading={loadingSystems.has(system.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Metrics — only show when QuWARTS is visible */}
      {visibleSystems.has("ours") && (
        <div className="h-[220px] border-t border-slate-200 bg-white shrink-0">
          <MetricsDashboard
            history={mockHistory}
            systems={renderedSystems.filter((s) => visibleSystems.has(s.id))}
            activeMetric={activeMetric}
            onMetricChange={setActiveMetric}
          />
        </div>
      )}
    </main>
  );
}
