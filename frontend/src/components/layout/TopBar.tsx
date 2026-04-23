"use client";

import { useState, useRef, useEffect } from "react";
import { Database, ListFilter, ShieldCheck, Zap, Plus, ChevronDown, X } from "lucide-react";

interface TopBarProps {
  dataset: string;
  workload: string;
  baselines: string[];
  onDatasetChange: (val: string) => void;
  onWorkloadChange: (val: string) => void;
  onAddBaseline: (val: string) => void;
  onRemoveBaseline: (val: string) => void;
}

const DATASETS = [
  { value: "nba", label: "NBA Dataset" },
  { value: "finance", label: "Finance Dataset" },
  { value: "healthcare", label: "Healthcare Dataset" },
  { value: "cs_lit", label: "CS Literature Dataset" },
  { value: "art", label: "Art Dataset" },
  { value: "legal", label: "Legal Dataset" },
];

const WORKLOADS: Record<string, { value: string; label: string }[]> = {
  nba: [
    { value: "players", label: "Player Analytics" },
    { value: "teams",   label: "Team Performance" },
    { value: "coaches", label: "Coaching Records" },
    { value: "cities",  label: "City & Arena Stats" },
  ],
  finance: [
    { value: "earnings",     label: "Earnings Summaries" },
    { value: "transactions", label: "Transaction Logs" },
  ],
  healthcare: [
    { value: "claims",   label: "Claims Review" },
    { value: "patients", label: "Patient Outcomes" },
  ],
  cs_lit: [
    { value: "papers",  label: "Paper Citations" },
    { value: "authors", label: "Author Profiles" },
  ],
  art: [
    { value: "artworks", label: "Artwork Catalogue" },
    { value: "artists",  label: "Artist Biographies" },
  ],
  legal: [
    { value: "contracts", label: "Contract Analysis" },
    { value: "cases",     label: "Case Precedents" },
  ],
};

const BASELINES = [
  { value: "squid", label: "SQUiD" },
  { value: "redd", label: "ReDD" },
  { value: "docetl", label: "DocETL" },
  { value: "quest", label: "QUEST" },
  { value: "palimpzest", label: "Palimpzest" },
];

function Dropdown({
  label,
  icon,
  value,
  options,
  onChange,
  placeholder,
}: {
  label: string;
  icon: React.ReactNode;
  value: string;
  options: { value: string; label: string }[];
  onChange: (val: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="flex flex-col gap-0.5" ref={ref}>
      <span className="text-[9px] uppercase font-black text-slate-400 ml-1 tracking-tighter">{label}</span>
      <div className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 hover:bg-slate-100 transition-colors"
        >
          <span className="shrink-0">{icon}</span>
          <div className="flex h-7 w-[130px] items-center justify-between rounded-md bg-white px-2 text-xs font-bold text-slate-700">
            <span className="truncate">{selected?.label ?? placeholder ?? "Select…"}</span>
            <ChevronDown className={`h-3.5 w-3.5 text-slate-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
          </div>
        </button>
        {open && (
          <div className="absolute top-full left-0 mt-1 z-50 min-w-[180px] rounded-lg border border-slate-200 bg-white shadow-lg overflow-hidden">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { onChange(opt.value); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-xs font-semibold hover:bg-slate-50 transition-colors ${
                  value === opt.value ? "bg-emerald-50 text-emerald-700" : "text-slate-700"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function TopBar({
  dataset,
  workload,
  baselines,
  onDatasetChange,
  onWorkloadChange,
  onAddBaseline,
  onRemoveBaseline,
}: TopBarProps) {
  const [baselineOpen, setBaselineOpen] = useState(false);
  const baselineRef = useRef<HTMLDivElement>(null);
  const workloadOptions = WORKLOADS[dataset] ?? WORKLOADS["nba"];
  const availableBaselines = BASELINES.filter((b) => !baselines.includes(b.value));

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (baselineRef.current && !baselineRef.current.contains(e.target as Node)) setBaselineOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header className="z-50 w-full border-b border-slate-200 px-6 py-2 flex items-center bg-white/80 backdrop-blur-md">
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0">
        <div className="p-1.5 bg-emerald-50 rounded-lg border border-emerald-100">
          <Zap className="w-5 h-5 text-emerald-600" />
        </div>
        <div>
          <h1 className="text-lg font-black tracking-tighter text-slate-900">QuWARTS</h1>
           </div>
      </div>

      <div className="h-8 w-[1px] bg-slate-200 mx-6 shrink-0" />

      {/* Left: Target Dataset + Query Workload */}
      <div className="flex items-center gap-4">
        <Dropdown
          label="Target Dataset"
          icon={<Database className="w-3.5 h-3.5 text-blue-600" />}
          value={dataset}
          options={DATASETS}
          onChange={(v) => { onDatasetChange(v); onWorkloadChange(WORKLOADS[v]?.[0]?.value ?? ""); }}
        />
        <Dropdown
          label="Query Workload"
          icon={<ListFilter className="w-3.5 h-3.5 text-emerald-600" />}
          value={workload}
          options={workloadOptions}
          onChange={onWorkloadChange}
        />
      </div>

      {/* Right: Compare Baselines */}
      <div className="ml-auto flex flex-col gap-0.5" ref={baselineRef}>
        <span className="text-[9px] uppercase font-black text-slate-400 ml-1 tracking-tighter">Compare Baselines</span>
        <div className="flex items-center gap-2">
          {/* Active baseline chips */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {baselines.map((b) => {
              const bl = BASELINES.find((x) => x.value === b);
              return (
                <div key={b} className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 h-9">
                  <ShieldCheck className="w-3 h-3 text-amber-600 shrink-0" />
                  <span className="text-xs font-bold text-slate-700">{bl?.label ?? b}</span>
                  <button onClick={() => onRemoveBaseline(b)} className="ml-0.5 text-slate-400 hover:text-red-500 transition-colors">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
          {/* Add baseline button */}
          <div className="relative">
            <button
              onClick={() => setBaselineOpen((o) => !o)}
              disabled={availableBaselines.length === 0}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors disabled:opacity-40"
            >
              <Plus className="w-4 h-4" />
            </button>
            {baselineOpen && availableBaselines.length > 0 && (
              <div className="absolute top-full right-0 mt-1 z-50 min-w-[150px] rounded-lg border border-slate-200 bg-white shadow-lg overflow-hidden">
                {availableBaselines.map((bl) => (
                  <button
                    key={bl.value}
                    onClick={() => { onAddBaseline(bl.value); setBaselineOpen(false); }}
                    className="w-full text-left px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    {bl.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
