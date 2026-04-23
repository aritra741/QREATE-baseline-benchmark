"use client";

import { System, SystemMetrics } from "@/types";
import { Clock, Target, Activity, FileCheck, FileX, FileDiff, Zap, Timer } from "lucide-react";
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from "@/components/ui/table";

interface SystemColumnProps {
  system: System;
  metrics?: SystemMetrics;
  results?: any[];
  gtResults?: any[];
  loading?: boolean;
}

export function SystemColumn({ system, metrics, results, gtResults, loading }: SystemColumnProps) {
  const displayRows = (results?.map((row: any) => {
    if (row.__comparisonStatus) return row;
    const matchingGT = gtResults?.find((gt: any) => gt.team_name === row.team_name);
    return { ...row, __comparisonStatus: matchingGT ? "match" : "extra" };
  }) || []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "match": return "bg-emerald-50 text-emerald-700 border-emerald-100";
      case "extra": return "bg-red-50 text-red-700 border-red-100";
      case "missing": return "bg-amber-50 text-amber-700 border-amber-100 opacity-60 italic";
      default: return "hover:bg-slate-50 text-slate-700";
    }
  };

  const noPreprocessing = metrics?.preprocessingTime === "No Preprocessing Needed";

  const formatRuntime = (seconds: number) => {
    if (seconds >= 60) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.round(seconds % 60);
      return `${mins} minutes ${secs} seconds`;
    }
    return `${seconds}s`;
  };

  const formatTokens = (tokens: number) => {
    return tokens.toLocaleString();
  };

  return (
    <div className="flex flex-col flex-1 min-w-[280px] border-r border-slate-200 h-full bg-white justify-between">
      {/* Header */}
      <div className="p-4 border-b border-slate-200 bg-slate-50 relative overflow-hidden flex flex-col justify-center" style={{ minHeight: "85px" }}>
        <div 
          className="absolute top-0 left-0 w-full h-1" 
          style={{ backgroundColor: system.color }} 
        />
        <h3 className="font-black uppercase tracking-widest text-sm mb-1.5" style={{ color: system.color }}>
          {system.name}
        </h3>
        
        {noPreprocessing ? (
          <div className="flex items-center gap-2 text-slate-400">
            <Clock className="w-3 h-3" />
            <span className="text-[10px] font-mono">No Preprocessing Needed</span>
          </div>
        ) : metrics ? (
          <div className="flex items-center gap-2">
            <Clock className="w-3 h-3 text-slate-400" />
            <span className="text-[10px] font-mono text-slate-500">Preprocessing time: {metrics.preprocessingTime}</span>
          </div>
        ) : (
          <div className="h-4" />
        )}
      </div>

      {/* Result Table */}
      <div className="overflow-y-auto custom-scrollbar p-0 flex flex-col">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            <div className="w-7 h-7 rounded-full border-[3px] border-slate-200 border-t-emerald-500 animate-spin" />
            <span className="text-[10px] text-slate-400 font-medium">Running {system.name}…</span>
          </div>
        ) : results && results.length > 0 ? (
          <Table className="w-full">
            <TableHeader className="bg-slate-50 sticky top-0 z-10">
              <TableRow className="hover:bg-transparent border-slate-200">
                {Object.keys(results[0] || {})
                  .filter((key) => key !== "__comparisonStatus")
                  .map((key) => (
                  <TableHead key={key} className="text-[9px] uppercase font-black text-slate-400 tracking-tight h-8 px-4">
                    {key.replace(/_/g, " ")}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody className="[&_tr:last-child]:border-0">
              {displayRows?.map((row, idx) => {
                const statusColor = getStatusColor(row.__comparisonStatus);
                return (
                  <TableRow 
                    key={idx} 
                    className={`border-slate-100 h-10 ${statusColor}`}
                  >
                    {Object.keys(row).filter(k => k !== '__comparisonStatus').map((key) => (
                      <TableCell key={key} className="text-xs font-mono py-0 px-4">
                        {row[key as keyof typeof row]}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <div className="flex items-center justify-center h-40 text-slate-400 italic text-xs">
            No results available
          </div>
        )}
      </div>

      {/* Footer Metrics */}
      {metrics && (
        <div className="p-4 bg-slate-50 border-t border-slate-200 space-y-3">
          {/* Precision / Recall / F1 */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded-lg bg-white border border-slate-200 shadow-sm">
              <div className="flex items-center gap-1 mb-1">
                <Target className="w-2.5 h-2.5 text-emerald-600" />
                <span className="text-[8px] uppercase font-bold text-slate-500">Prec.</span>
              </div>
              <div className="text-xs font-black text-slate-900">{Math.round(metrics.precision * 100)}%</div>
            </div>
            <div className="p-2 rounded-lg bg-white border border-slate-200 shadow-sm">
              <div className="flex items-center gap-1 mb-1">
                <Activity className="w-2.5 h-2.5 text-blue-600" />
                <span className="text-[8px] uppercase font-bold text-slate-500">Recall</span>
              </div>
              <div className="text-xs font-black text-slate-900">{Math.round(metrics.recall * 100)}%</div>
            </div>
            <div className="p-2 rounded-lg bg-white border border-slate-200 shadow-sm">
              <div className="flex items-center gap-1 mb-1">
                <Zap className="w-2.5 h-2.5 text-amber-600" />
                <span className="text-[8px] uppercase font-bold text-slate-500">F1</span>
              </div>
              <div className="text-xs font-black text-slate-900">{Math.round(metrics.f1 * 100)}%</div>
            </div>
          </div>

          {/* Row breakdown */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <FileCheck className="w-3 h-3 text-emerald-600" />
                <span className="text-[10px] text-slate-600 font-medium">Matching Ground Truth</span>
              </div>
              <span className="text-[10px] font-mono text-emerald-700 font-bold">{metrics.matchingRows}</span>
            </div>
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <FileX className="w-3 h-3 text-red-600" />
                <span className="text-[10px] text-slate-600 font-medium">Extra Rows (False Positive)</span>
              </div>
              <span className="text-[10px] font-mono text-red-700 font-bold">{metrics.rowsInSystemNotGT}</span>
            </div>
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <FileDiff className="w-3 h-3 text-amber-600" />
                <span className="text-[10px] text-slate-600 font-medium">Missing Rows (False Negative)</span>
              </div>
              <span className="text-[10px] font-mono text-amber-700 font-bold">{metrics.rowsInGTNotSystem}</span>
            </div>
          </div>

          {/* Runtime + Tokens */}
          <div className="pt-2 border-t border-slate-200 space-y-1">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-1.5">
                <Timer className="w-3 h-3 text-slate-400" />
                <span className="text-[10px] uppercase font-black text-slate-400 tracking-widest">Runtime</span>
              </div>
              <span className="text-xs font-mono font-bold text-emerald-600">{formatRuntime(metrics.runtime)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[10px] uppercase font-black text-slate-400 tracking-widest">Tokens Used</span>
              <span className="text-xs font-mono font-bold text-slate-600">{formatTokens(metrics.tokensUsed)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
