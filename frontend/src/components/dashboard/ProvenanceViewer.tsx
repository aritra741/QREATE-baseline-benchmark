"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  X, 
  FileText, 
  Search, 
  Code, 
  CheckCircle2, 
  ArrowRight,
  Info,
  ShieldCheck,
  Zap,
  Loader2,
  Layers
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export function ProvenanceViewer({ data, onClose }: { data: any; onClose: () => void }) {
  const [isVerifying, setIsVerifying] = useState(false);
  const [isVerified, setIsVerified] = useState(false);

  if (!data) return null;

  const handleVerify = () => {
    setIsVerifying(true);
    setTimeout(() => {
      setIsVerifying(false);
      setIsVerified(true);
    }, 1500);
  };

  return (
    <motion.div 
      initial={{ y: "100%" }}
      animate={{ y: 0 }}
      exit={{ y: "100%" }}
      transition={{ type: "spring", damping: 30, stiffness: 200 }}
      className="fixed bottom-0 left-0 right-0 z-[100] h-[500px] bg-slate-950/95 backdrop-blur-xl border-t border-white/20 rounded-t-[32px] shadow-[0_-20px_100px_rgba(0,0,0,0.8)] overflow-hidden"
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="px-8 py-5 border-b border-white/10 flex items-center justify-between bg-white/5">
          <div className="flex items-center gap-4">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
              <ShieldCheck className="w-6 h-6 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-white tracking-tight">Provenance Deep-Dive</h2>
                <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 uppercase text-[9px] font-black tracking-widest px-2">
                  Query-Aware
                </Badge>
              </div>
              <p className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mt-0.5">
                Attribute: <span className="text-emerald-400">{data.attribute.toUpperCase()}</span> • Value: <span className="text-slate-300">{data.value}</span>
              </p>
            </div>
          </div>
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={onClose}
            className="rounded-full hover:bg-white/10 transition-colors h-10 w-10"
          >
            <X className="w-6 h-6" />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Document Evidence */}
          <div className="flex-1 p-8 overflow-y-auto border-r border-white/10">
            <div className="flex items-center gap-2 mb-6">
              <FileText className="w-4 h-4 text-emerald-500" />
              <span className="text-[11px] font-black uppercase tracking-widest text-slate-400">Evidence Source: {data.source || 'Medical_Report_001.pdf'}</span>
            </div>
            <div className="relative">
              <p className="text-slate-200 leading-relaxed text-base bg-white/5 p-6 rounded-2xl border border-white/5 shadow-inner">
                The clinical summary indicates that the patient was admitted following a duplicate claim incident. 
                <motion.span 
                  initial={{ backgroundColor: "rgba(16, 185, 129, 0)" }}
                  animate={{ backgroundColor: "rgba(16, 185, 129, 0.2)" }}
                  transition={{ delay: 0.5, duration: 1 }}
                  className="px-1.5 py-1 rounded border border-emerald-500/40 text-white font-semibold glow-emerald"
                >
                  {data.attribute === 'cost' 
                    ? `The total cost for the surgery was roughly five hundred dollars`
                    : `The status was explicitly marked as '${data.value}' by the auditing department`}
                </motion.span>, 
                which was processed under the {data.details || 'standard protocol'}. 
                Cross-referencing with the workload predicates ensures alignment with SQL constraints.
              </p>
              
              <div className="mt-8 flex gap-4">
                {data.attribute === 'status' && (
                  <div className="flex-1 p-4 rounded-xl bg-blue-500/5 border border-blue-500/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Zap className="w-3.5 h-3.5 text-blue-400" />
                      <span className="text-[10px] font-bold text-blue-400 uppercase tracking-tighter">SQL Constraint Awareness</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      The engine used the <code className="text-blue-300 font-mono">WHERE Status = &apos;Denied&apos;</code> predicate to filter out non-matching status candidates from the raw text.
                    </p>
                  </div>
                )}
                {data.attribute === 'cost' && (
                  <div className="flex-1 p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Layers className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-tighter">Normalization Intelligence</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Since the SQL expected a numeric result for <code className="text-emerald-300 font-mono">AVG(cost)</code>, the engine knew to normalize text to float.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right: Smart Normalization */}
          <div className="w-[450px] p-8 space-y-8 bg-black/40">
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <Code className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-black uppercase tracking-widest text-slate-500">Query-Aware Normalization</span>
              </div>
              
              <div className="space-y-3">
                <div className="p-4 bg-white/5 border border-white/5 rounded-2xl relative group overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500" />
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-slate-500 font-bold uppercase">Raw Text Segment</span>
                      </div>
                    <div className="flex items-center gap-4 bg-black/40 p-3 rounded-lg border border-white/5">
                      <span className="text-xs text-slate-300 italic font-mono">
                        {data.attribute === 'cost' ? '"roughly five hundred dollars"' : `"${data.value}"`}
                      </span>
                      <ArrowRight className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span className="text-lg font-black text-emerald-400 font-mono">
                        {data.attribute === 'cost' ? '500.00' : data.value}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-4 bg-white/5 border border-white/5 rounded-2xl relative group overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-blue-500" />
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-slate-500 font-bold uppercase">Semantic Constraints</span>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                        <p className="text-[11px] text-slate-300">Target Type: <code className="text-blue-400">{data.attribute === 'cost' ? 'NUMERIC' : 'VARCHAR'}</code></p>
                      </div>
                      {data.attribute === 'cost' && (
                        <div className="flex items-center gap-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                          <p className="text-[11px] text-slate-300">Unit Normalization: <code className="text-blue-400">USD ($)</code></p>
                        </div>
                      )}
                      {data.attribute === 'status' && (
                        <div className="flex items-center gap-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                          <p className="text-[11px] text-slate-300">Case Sensitivity: <code className="text-blue-400">Insensitive</code></p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
