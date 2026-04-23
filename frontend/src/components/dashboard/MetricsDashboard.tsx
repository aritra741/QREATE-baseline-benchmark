"use client";

import { System, QueryResult } from "@/types";
import { Activity, BarChart3 } from "lucide-react";

interface MetricsDashboardProps {
  history: QueryResult[];
  systems: System[];
  activeMetric: "precision" | "recall" | "f1" | "runtime";
  onMetricChange: (metric: any) => void;
}

export function MetricsDashboard({ 
  history, 
  systems, 
  activeMetric, 
  onMetricChange 
}: MetricsDashboardProps) {
  // Transform history data for grouped bar chart
  const chartData = history.map(h => {
    const entry: any = { name: h.queryId.toUpperCase() };
    systems.forEach(s => {
      if (!s.isGT) {
        entry[s.id] = h.metrics[s.id]?.[activeMetric] || 0;
      }
    });
    return entry;
  });

  // Calculate Average data
  const avgData: any = { name: "AVG" };
  systems.forEach(s => {
    if (!s.isGT) {
      const sum = history.reduce((acc, h) => {
        const val = h.metrics[s.id]?.[activeMetric];
        return acc + (typeof val === 'number' ? val : 0);
      }, 0);
      avgData[s.id] = sum / history.length;
    }
  });

  const metricLabels = {
    precision: "Precision (%)",
    recall: "Recall (%)",
    f1: "F1 Score (%)",
    runtime: "Runtime (s)"
  };

  const comparisonSystems = systems.filter((s) => !s.isGT);
  const allValues: number[] = [];
  chartData.forEach((row) => {
    comparisonSystems.forEach((s) => {
      allValues.push(Number(row[s.id] ?? 0));
    });
  });
  comparisonSystems.forEach((s) => {
    allValues.push(Number(avgData[s.id] ?? 0));
  });
  const maxValue = Math.max(1, ...allValues);
  const barAreaHeightPx = 98;
  const barHeightPx = (value: number) =>
    `${Math.max(10, Math.round((Math.max(0, value) / maxValue) * barAreaHeightPx))}px`;

  return (
    <div className="flex h-full bg-white">
      {/* Metric Selector (Left) */}
      <div className="w-[220px] border-r border-slate-200 p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2 mb-2 px-1">
          <Activity className="w-3.5 h-3.5 text-emerald-600" />
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Metric</span>
        </div>
        {(['precision', 'recall', 'f1', 'runtime'] as const).map((m) => (
          <button
            key={m}
            onClick={() => onMetricChange(m)}
            className={`text-left px-3 py-2 rounded-lg text-[11px] font-bold uppercase tracking-tighter ${
              activeMetric === m 
              ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/20' 
              : 'text-slate-500 bg-white border border-transparent'
            }`}
          >
            {m === 'f1' ? 'F1 Score' : m.charAt(0).toUpperCase() + m.slice(1)}
          </button>
        ))}
      </div>

      {/* Main Chart (Center) */}
      <div className="flex-1 p-6 relative">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-slate-400" />
            <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">
              Comparative Analysis: <span className="text-slate-900">{metricLabels[activeMetric]}</span>
            </h3>
          </div>
          <div className="flex items-center gap-4">
            {systems.filter(s => !s.isGT).map(s => (
              <div key={s.id} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
                <span className="text-[10px] font-bold text-slate-500 uppercase">{s.name}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="h-[160px] w-full">
          <div className="h-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex h-[118px] items-end justify-between gap-4">
              {chartData.map((row) => (
                <div key={row.name} className="flex flex-1 items-end justify-center gap-1.5">
                  {comparisonSystems.map((s) => (
                    <div
                      key={`${row.name}-${s.id}`}
                      className="w-3 rounded-t-sm shadow-[0_2px_4px_rgba(0,0,0,0.1)]"
                      style={{ backgroundColor: s.color, height: barHeightPx(Number(row[s.id] ?? 0)) }}
                    />
                  ))}
                </div>
              ))}
            </div>
            <div className="mt-0.5 flex items-center gap-4 px-1">
              {chartData.map((row) => (
                <div key={`label-${row.name}`} className="flex-1 text-center">
                  <span className="text-[10px] font-black uppercase text-slate-400">{row.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Average Chart (Right) */}
      <div className="w-[200px] border-l border-slate-200 p-6 flex flex-col items-center">
        <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-6">Aggregate</span>
        <div className="h-[160px] w-full">
          <div className="h-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex h-[118px] items-end justify-center gap-2">
              {comparisonSystems.map((s) => (
                <div
                  key={`avg-${s.id}`}
                  className="w-4 rounded-t-sm shadow-[0_2px_4px_rgba(0,0,0,0.1)]"
                  style={{ backgroundColor: s.color, height: barHeightPx(Number(avgData[s.id] ?? 0)) }}
                />
              ))}
            </div>
            <div className="mt-2 text-center text-[10px] font-black uppercase text-slate-400">AVG</div>
          </div>
        </div>
        <div className="mt-2 text-center">
          <span className="text-[10px] font-black text-slate-400 uppercase">AVG Score</span>
        </div>
      </div>
    </div>
  );
}
