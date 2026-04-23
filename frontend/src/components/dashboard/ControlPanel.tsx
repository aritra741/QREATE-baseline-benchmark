"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Settings, Terminal, Zap } from "lucide-react";

interface ControlPanelProps {
  currentQueryId: string;
  onQuerySelect: (id: string) => void;
  customQuery: string;
  onCustomQueryChange: (val: string) => void;
  entityResolution: string;
  onEntityResolutionChange: (val: string) => void;
  llm: string;
  onLlmChange: (val: string) => void;
  workloadSelected: boolean;
}

const ENTITY_RESOLUTION_OPTIONS = [
  { value: "blink",    label: "BLINK" },
  { value: "refined",  label: "ReFinED" },
  { value: "rel",      label: "REL" },
  { value: "elq",      label: "ELQ" },
  { value: "mrefined", label: "mReFinED" },
];

const LLM_OPTIONS = [
  { value: "qwen2.5-7b", label: "Qwen2.5:7b-instruct" },
  { value: "gpt-4o", label: "GPT-4o" },
  { value: "llama3-8b", label: "Llama3:8b" },
  { value: "mistral-7b", label: "Mistral:7b" },
];

const NBA_WORKLOAD = [
  {
    id: "Q1",
    sql: `SELECT t.team_name, t.location, COUNT(p.name) as\nplayer_count FROM player p JOIN team t ON\np.team = t.team_name WHERE p.draft_year > 2000\nOR p.position = 'Frontcourt' OR t.founded_year < 1980\nOR p.age > 30 GROUP BY t.team_name, t.location, t.founded_year;`,
  },
  {
    id: "Q2",
    sql: "SELECT * player WHERE age > 25",
  },
];

function KnobDropdown({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (val: string) => void;
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
    <div className="space-y-0" ref={ref}>
      <label className="text-[8px] font-bold text-slate-500 uppercase tracking-widest ml-1">{label}</label>
      <div className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex h-6 w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-2 text-[9px] font-bold text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <span>{selected?.label ?? "Select…"}</span>
          <ChevronDown className={`h-3.5 w-3.5 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div className="absolute top-full left-0 mt-1 z-50 w-full rounded-lg border border-slate-200 bg-white shadow-lg overflow-hidden">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { onChange(opt.value); setOpen(false); }}
                className={`w-full text-left px-2 py-1.5 text-[9px] font-semibold hover:bg-slate-50 transition-colors ${
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

export function ControlPanel({
  currentQueryId,
  onQuerySelect,
  customQuery,
  onCustomQueryChange,
  entityResolution,
  onEntityResolutionChange,
  llm,
  onLlmChange,
  workloadSelected,
}: ControlPanelProps) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      {/* Query Selection */}
      <div className="space-y-1 p-2.5">
        <div className="mb-0.5 flex items-center gap-1.5">
          <Terminal className="h-3.5 w-3.5 text-emerald-600" />
          <h2 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Query Selection</h2>
        </div>

        <div className="space-y-0.5">
          <label className="text-[9px] font-black uppercase tracking-widest text-slate-500 ml-1">Custom Query</label>
          <div className="group relative">
            <textarea
              value={customQuery}
              onChange={(e) => onCustomQueryChange(e.target.value)}
              placeholder="SELECT * FROM Claims WHERE..."
              className="h-9 w-full resize-none rounded-lg border border-slate-200 bg-slate-50 p-2 pr-16 font-mono text-[9px] leading-tight text-slate-700 outline-none placeholder:text-slate-400 focus:ring-1 focus:ring-emerald-500/50"
            />
            <button className="absolute bottom-1.5 right-1.5 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[9px] font-bold text-emerald-700 transition-all active:scale-95 hover:bg-emerald-500/20">
              Submit
            </button>
          </div>
        </div>

        {workloadSelected && (
          <div className="space-y-0.5 pt-0.5">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-500 ml-1">Preset Workload</label>
            <div className="space-y-0.5">
              {NBA_WORKLOAD.map((q) => (
                <button
                  key={q.id}
                  onClick={() => onQuerySelect(q.id)}
                  className={`w-full text-left p-1.5 rounded-md border ${
                    currentQueryId === q.id ? "bg-emerald-50 border-emerald-200" : "bg-white border-slate-100"
                  }`}
                >
                  <div className="mb-0.5 flex items-start justify-between">
                    <span className={`text-[9px] font-black uppercase tracking-widest ${
                      currentQueryId === q.id ? "text-emerald-700" : "text-slate-500"
                    }`}>{q.id}</span>
                    {currentQueryId === q.id && (
                      <div className="w-1 h-1 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,1)]" />
                    )}
                  </div>
                  <p className={`whitespace-pre-wrap text-[9px] font-mono leading-tight ${
                    currentQueryId === q.id ? "text-emerald-900" : "text-slate-500"
                  }`}>{q.sql}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* System Knobs */}
      <div className="border-t border-slate-200 p-2.5 space-y-1">
        <div className="mb-0.5 flex items-center gap-1.5">
          <Settings className="h-3.5 w-3.5 text-blue-600" />
          <h2 className="text-[10px] font-black uppercase tracking-widest text-slate-400">System Knobs</h2>
        </div>
        <div className="space-y-1">
          <KnobDropdown
            label="Entity Resolution"
            value={entityResolution}
            options={ENTITY_RESOLUTION_OPTIONS}
            onChange={onEntityResolutionChange}
          />
          <KnobDropdown
            label="LLM"
            value={llm}
            options={LLM_OPTIONS}
            onChange={onLlmChange}
          />
        </div>
      </div>
    </div>
  );
}
