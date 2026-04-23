"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Code, 
  Database, 
  Cpu, 
  Zap, 
  ArrowRight,
  Shield,
  Table as TableIcon,
  TrendingUp,
  Clock,
  Coins,
  Link
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import schemaData from "@/data/dummySchema.json";
import CountUp from "react-countup";

export function PreprocessingView({ 
  onComplete,
  baseline
}: { 
  onComplete: () => void;
  baseline: string;
}) {
  const [isFinished, setIsFinished] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsFinished(true);
    }, 1500); // Fast transition to show results
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="p-12 max-w-5xl mx-auto space-y-12 pb-20">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h2 className="text-3xl font-black text-white tracking-tight">System Initialization Complete</h2>
          <p className="text-slate-400 text-sm">Workload patterns analyzed and extraction schema inferred.</p>
        </div>
        <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 px-4 py-1.5 font-black uppercase tracking-widest text-[10px]">
          Engine Ready
        </Badge>
      </div>

      <div className="grid grid-cols-12 gap-8">
        {/* Left Column: Inferred Schema */}
        <div className="col-span-7 space-y-8">
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <TableIcon className="w-4 h-4 text-emerald-400" />
              </div>
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-300">Inferred Extraction Schema</h3>
            </div>
          </div>
          
          <div className="space-y-4 max-h-[450px] overflow-y-auto pr-2 custom-scrollbar">
            {schemaData.tables.map((table, tableIdx) => (
              <div key={table.name} className="glass-panel rounded-2xl border-white/10 overflow-hidden">
                <div className="bg-emerald-500/10 px-6 py-2 border-b border-emerald-500/20 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Database className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-[11px] font-black uppercase tracking-widest text-emerald-400">Table: {table.name}</span>
                  </div>
                  <Badge variant="outline" className="text-[8px] border-emerald-500/30 text-emerald-400/70">
                    {table.columns.length} Attributes
                  </Badge>
                </div>
                <div className="grid grid-cols-12 bg-white/5 px-6 py-2 border-b border-white/5">
                  <div className="col-span-4 text-[9px] uppercase font-black text-slate-500 tracking-widest">Attribute</div>
                  <div className="col-span-3 text-[9px] uppercase font-black text-slate-500 tracking-widest">Type</div>
                  <div className="col-span-5 text-[9px] uppercase font-black text-slate-500 tracking-widest">Semantic Role</div>
                </div>
                <div className="divide-y divide-white/5">
                  {table.columns.map((col: any, idx) => (
                    <motion.div 
                      key={col.name}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: (tableIdx * 0.2) + (idx * 0.05) }}
                      className="grid grid-cols-12 px-6 py-3 items-center hover:bg-white/5 transition-colors group"
                    >
                      <div className="col-span-4 flex items-center gap-2">
                        <div className={`w-1 h-1 rounded-full ${col.references ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)]' : 'bg-emerald-500/30 group-hover:bg-emerald-500'} transition-colors`} />
                        <span className={`text-[12px] font-mono font-bold ${col.references ? 'text-amber-200' : 'text-slate-200'}`}>{col.name}</span>
                        {col.references && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger>
                                <Link className="w-3 h-3 text-amber-400/60" />
                              </TooltipTrigger>
                              <TooltipContent className="text-[10px] bg-slate-900 border-white/10 text-slate-200">
                                Foreign Key: references {col.references}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                      <div className="col-span-3 flex items-center gap-2">
                        <Badge variant="outline" className={`text-[8px] font-black tracking-widest ${col.references ? 'bg-amber-500/5 text-amber-400 border-amber-500/20' : 'bg-blue-500/5 text-blue-400 border-blue-500/20'} py-0 px-1.5 uppercase h-4`}>
                          {col.type}
                        </Badge>
                        {col.references && <span className="text-[8px] font-black text-amber-500/50 tracking-tighter">FK</span>}
                      </div>
                      <div className="col-span-5">
                        <span className="text-[10px] text-slate-400 font-medium line-clamp-1">
                          {col.references ? (
                            <span className="flex items-center gap-1">
                              {col.semantic} <ArrowRight className="w-2 h-2 text-slate-600" /> <span className="text-amber-400/70">{col.references}</span>
                            </span>
                          ) : col.semantic}
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Table Relationships Visualization */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="p-5 rounded-2xl bg-amber-500/[0.03] border border-amber-500/10 space-y-4"
          >
            <div className="flex items-center gap-2">
              <Link className="w-3.5 h-3.5 text-amber-400" />
              <h4 className="text-[10px] font-black uppercase tracking-widest text-amber-400/80">Inferred Join Graph</h4>
            </div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10">
                <Database className="w-3 h-3 text-slate-500" />
                <span className="text-xs font-bold text-slate-200">Claims</span>
              </div>
              <div className="flex-1 h-[1px] bg-gradient-to-r from-emerald-500/50 via-amber-500/50 to-blue-500/50 relative">
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 text-[8px] font-black text-amber-400 uppercase tracking-tighter bg-slate-950 px-2 whitespace-nowrap">
                  provider_id ⟷ id
                </div>
                <div className="absolute -right-1 -top-1 w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                <div className="absolute -left-1 -top-1 w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10">
                <Database className="w-3 h-3 text-slate-500" />
                <span className="text-xs font-bold text-slate-200">Providers</span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Right Column: Preprocessing Comparison */}
        <div className="col-span-5 space-y-6">
          <div className="flex items-center gap-3 px-2">
            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <TrendingUp className="w-4 h-4 text-blue-400" />
            </div>
            <h3 className="text-xs font-black uppercase tracking-widest text-slate-300">Initialization Metrics</h3>
          </div>

          <div className="space-y-4">
            {/* Initialization Time */}
            <div className="glass-panel p-6 rounded-3xl border-white/5 space-y-6">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] uppercase font-black text-slate-500 tracking-widest">Initialization Time</span>
                  <div className="flex items-center gap-2">
                    <Clock className="w-3 h-3 text-slate-500" />
                    <span className="text-xs font-bold text-emerald-400">8.4s</span>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] font-bold">
                      <span className="text-slate-400">Q-ANSWER (Consolidated)</span>
                      <span className="text-white">8.4s</span>
                    </div>
                    <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500 rounded-full w-[45%]" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] font-bold">
                      <span className="text-slate-400">{baseline}</span>
                      <span className="text-white">18.2s</span>
                    </div>
                    <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full bg-slate-700 rounded-full w-full" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Token Consumption */}
              <div className="space-y-4 pt-4 border-t border-white/5">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] uppercase font-black text-slate-500 tracking-widest">Initial Token Usage</span>
                  <div className="flex items-center gap-2">
                    <Coins className="w-3 h-3 text-slate-500" />
                    <span className="text-xs font-bold text-emerald-400">12,540</span>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] font-bold">
                      <span className="text-slate-400">Q-ANSWER</span>
                      <span className="text-white">12k</span>
                    </div>
                    <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500 rounded-full w-[25%]" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] font-bold">
                      <span className="text-slate-400">Baseline</span>
                      <span className="text-white">48k</span>
                    </div>
                    <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full bg-slate-700 rounded-full w-full" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <Button 
              onClick={onComplete}
              className="w-full h-16 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white font-black uppercase tracking-widest text-sm glow-emerald shadow-2xl transition-all"
            >
              Enter Query Stage
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
