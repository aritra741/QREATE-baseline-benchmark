"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Play, 
  Terminal, 
  CheckCircle2, 
  AlertCircle, 
  Layers, 
  Database,
  Cpu,
  Search,
  Filter,
  FileText,
  Workflow,
  MousePointer2,
  AlertTriangle,
  Zap,
  Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import dummyTables from "@/data/dummyTables.json";
import schemaData from "@/data/dummySchema.json";

const traceSteps = [
  { id: "parse", label: "Parse SQL", icon: Terminal },
  { id: "match", label: "Pattern Matching", icon: Workflow },
  { id: "delta", label: "Delta Detection", icon: Layers },
  { id: "process", label: "Dynamic Processing", icon: AlertCircle, isConditional: true },
  { id: "sieve", label: "Pruning", icon: Filter },
  { id: "llm", label: "LLM Extraction", icon: Cpu },
  { id: "exec", label: "Execution", icon: Database },
];

export interface QueryMetrics {
  tokens: { ours: number; baseline: number };
  latency: { ours: number; baseline: number };
  accuracy: { ours: number; baseline: number };
  recall: { ours: number; baseline: number };
  precision: { ours: number; baseline: number };
}

export function ExecutionPanel({ 
  onExecute, 
  onCellClick 
}: { 
  onExecute: (metrics: QueryMetrics) => void; 
  onCellClick: (cellData: any) => void;
}) {
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentStep, setCurrentStep] = useState<number>(-1);
  const [sql, setSql] = useState("SELECT AVG(cost)\nFROM Claims\nWHERE Status = 'Denied'");
  const [showResults, setShowResults] = useState(false);
  const [deltaType, setDeltaType] = useState<"none" | "row" | "column">("none");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isOutOfSchema, setIsOutOfSchema] = useState(false);
  const [cursorPosition, setCursorPosition] = useState({ top: 0, left: 0 });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [cursorIdx, setCursorIdx] = useState(0);

  // Schema-aware autocomplete logic
  useEffect(() => {
    if (!textareaRef.current) return;

    const textBeforeCursor = sql.substring(0, cursorIdx);
    const lastWordMatch = textBeforeCursor.match(/[\w]*$/);
    const lastWord = lastWordMatch ? lastWordMatch[0] : "";
    
    if (lastWord.length > 0) {
      const allCols = schemaData.tables.flatMap(t => t.columns.map(c => c.name));
      const allTables = schemaData.tables.map(t => t.name);
      const matches = Array.from(new Set([...allCols, ...allTables]))
        .filter(s => s.toLowerCase().startsWith(lastWord.toLowerCase()) && s.toLowerCase() !== lastWord.toLowerCase());
      setSuggestions(matches);
      
      // Update cursor position for suggestion box
      const linesBeforeCursor = textBeforeCursor.split("\n");
      const currentLineIndex = linesBeforeCursor.length - 1;
      const charIndexInLine = linesBeforeCursor[currentLineIndex].length;
      
      // Approximation of cursor position based on font metrics
      setCursorPosition({
        top: currentLineIndex * 22 + 24, // 22px line-height, 24px padding (p-6)
        left: charIndexInLine * 8.4 + 24 // 8.4px char-width, 24px padding (p-6)
      });
    } else {
      setSuggestions([]);
    }

    // Out-of-schema detection
    const tokens = sql.toLowerCase().split(/[\s,();]+/);
    const tables = new Set(schemaData.tables.map(t => t.name.toLowerCase()));
    const columns = new Set(schemaData.tables.flatMap(t => t.columns.map(c => c.name.toLowerCase())));
    const keywords = new Set([
      "select", "avg", "count", "sum", "max", "min", "from", "where", "group", "by", "join", "on", "and", "or", "=", "is", "not", "null", "limit", "as", "order", "asc", "desc", "between", "in", "like", "*", ">", "<", ">=", "<=", "!=", "<>"
    ]);
    
    let outOfBounds = false;
    for (let i = 0; i < tokens.length; i++) {
      const t = tokens[i];
      if (!t || t.match(/^['"]|^\d+$/)) continue;

      const prev = i > 0 ? tokens[i - 1] : "";
      
      // If follows FROM or JOIN, it MUST be a known table or a keyword (subquery start)
      if (prev === "from" || prev === "join") {
        if (!tables.has(t) && !keywords.has(t)) {
          outOfBounds = true;
          break;
        }
      } 
      // Otherwise it must be a keyword, table, or column
      else if (!keywords.has(t) && !tables.has(t) && !columns.has(t)) {
        outOfBounds = true;
        break;
      }
    }
    
    setIsOutOfSchema(outOfBounds);
  }, [sql, cursorIdx]);

  const runQuery = async () => {
    setIsExecuting(true);
    setShowResults(false);
    setCurrentStep(0);
    
    const lowerSql = sql.toLowerCase();
    let type: "none" | "row" | "column" = "none";
    if (isOutOfSchema || lowerSql.includes("details")) type = "column";
    else if (lowerSql.includes("region") || lowerSql.includes("2023")) type = "row";
    setDeltaType(type);

    const activeSteps = traceSteps.filter(s => !s.isConditional || (s.id === "process" && type !== "none"));

    for (let i = 0; i < activeSteps.length; i++) {
      setCurrentStep(traceSteps.indexOf(activeSteps[i]));
      await new Promise(resolve => setTimeout(resolve, 600));
    }
    
    setIsExecuting(false);
    setShowResults(true);
    
    // Generate realistic metrics with trade-offs
    const isComplex = isOutOfSchema;
    
    // Baseline metrics
    const baseTokens = Math.floor(Math.random() * 2000) + 1500;
    const baseLatency = Number((Math.random() * 2 + 1.5).toFixed(2));
    const baseAccuracy = Math.floor(Math.random() * 10) + 82;

    const metrics: QueryMetrics = {
      tokens: {
        // Q-ANSWER is almost always better on tokens (that's the core value prop)
        ours: isComplex 
          ? Math.floor(Math.random() * 400) + 800 // 800-1200
          : Math.floor(Math.random() * 200) + 200, // 200-400
        baseline: baseTokens
      },
      latency: {
        // TRADE-OFF: Complex planning can be SLOWER than naive execution
        ours: isComplex 
          ? Number((Math.random() * 3 + 3.5).toFixed(2)) // 3.5s - 6.5s (Slower than baseline)
          : Number((Math.random() * 0.8 + 0.8).toFixed(2)), // 0.8s - 1.6s (Faster)
        baseline: baseLatency // 1.5s - 3.5s
      },
      accuracy: {
        // TRADE-OFF: High-speed extraction might slightly miss nuances compared to direct LLM
        ours: isComplex
          ? Math.floor(Math.random() * 8) + 80 // 80-88% (Sometimes lower than baseline)
          : Math.floor(Math.random() * 5) + 94, // 94-99%
        baseline: baseAccuracy // 82-92%
      },
      recall: {
        ours: isComplex ? 75 + Math.random() * 10 : 96 + Math.random() * 4,
        baseline: 80 + Math.random() * 10
      },
      precision: {
        ours: isComplex ? 82 + Math.random() * 8 : 94 + Math.random() * 5,
        baseline: 85 + Math.random() * 10
      }
    };
    
    onExecute(metrics);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab' && suggestions.length > 0) {
      e.preventDefault();
      acceptSuggestion(suggestions[0]);
    }
  };

  const acceptSuggestion = (suggestion: string) => {
    const textBeforeCursor = sql.substring(0, cursorIdx);
    const lastWordMatch = textBeforeCursor.match(/[\w]*$/);
    const lastWord = lastWordMatch ? lastWordMatch[0] : "";
    
    const textBefore = sql.substring(0, cursorIdx - lastWord.length);
    const textAfter = sql.substring(cursorIdx);
    const newSql = textBefore + suggestion + " " + textAfter;
    
    setSql(newSql);
    const newCursorIdx = textBefore.length + suggestion.length + 1;
    setCursorIdx(newCursorIdx);
    setSuggestions([]);

    // Reset cursor in textarea after state update
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(newCursorIdx, newCursorIdx);
      }
    }, 0);
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setSql(e.target.value);
    setCursorIdx(e.target.selectionStart);
  };

  const handleCursorActivity = (e: React.SyntheticEvent<HTMLTextAreaElement>) => {
    setCursorIdx(e.currentTarget.selectionStart);
  };

  return (
    <div className="p-6 space-y-8 max-w-5xl mx-auto pb-20">
      {/* SQL Editor with Inline Autocomplete */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className={`glass-panel rounded-2xl p-1 overflow-hidden transition-all duration-500 relative ${
          isOutOfSchema ? 'ring-2 ring-yellow-500/50 shadow-[0_0_30px_rgba(234,179,8,0.1)]' : 'focus-within:ring-2 focus-within:ring-emerald-500/50'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-white/5">
          <div className="flex items-center gap-3">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/40" />
            </div>
            <span className="text-[10px] font-black font-mono text-slate-500 uppercase tracking-widest">SQL Editor</span>
            {isOutOfSchema && (
              <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 text-[9px] h-5 px-1.5 font-black uppercase tracking-tighter animate-pulse">
                New Logic Detected
              </Badge>
            )}
          </div>
          <Button 
            onClick={runQuery} 
            disabled={isExecuting}
            className={`h-8 gap-2 px-4 rounded-full shadow-lg transition-all active:scale-95 font-black uppercase tracking-widest text-[10px] ${
              isOutOfSchema ? 'bg-yellow-600 hover:bg-yellow-500 text-slate-950' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            {isExecuting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Execute
          </Button>
        </div>
        
        <div className="relative">
          <textarea 
            ref={textareaRef}
            value={sql}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            onKeyUp={handleCursorActivity}
            onMouseUp={handleCursorActivity}
            onSelect={handleCursorActivity}
            onClick={handleCursorActivity}
            className={`w-full h-44 bg-transparent p-6 font-mono text-sm outline-none resize-none leading-[22px] transition-colors ${
              isOutOfSchema ? 'text-yellow-100/90' : 'text-emerald-50/90'
            }`}
            spellCheck={false}
          />
          
          {/* Inline Autocomplete Suggestions */}
          <AnimatePresence>
            {suggestions.length > 0 && (
              <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                style={{ 
                  position: 'absolute',
                  top: cursorPosition.top,
                  left: cursorPosition.left,
                }}
                className="z-[60] min-w-[120px] glass-panel bg-slate-900/90 border-emerald-500/30 rounded-lg shadow-2xl overflow-hidden pointer-events-auto"
              >
                {suggestions.slice(0, 4).map((s, idx) => (
                  <button 
                    key={s}
                    onClick={() => acceptSuggestion(s)}
                    className="w-full text-left px-3 py-1.5 hover:bg-emerald-500/20 text-[11px] font-mono text-emerald-400 border-b border-white/5 last:border-0 transition-colors flex items-center justify-between group"
                  >
                    <span>{s}</span>
                    {idx === 0 && (
                      <span className="text-[9px] text-slate-600 group-hover:text-emerald-500/50 font-black">Tab</span>
                    )}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {/* Execution Trace Animation */}
      <AnimatePresence>
        {isExecuting && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="overflow-hidden bg-white/5 border border-white/5 rounded-2xl p-8"
          >
            <div className="flex items-center justify-between gap-2 px-2">
              {traceSteps.map((step, idx) => {
                const isActive = idx === currentStep;
                const isCompleted = idx < currentStep;
                const isSkipped = step.isConditional && deltaType === "none";
                
                if (isSkipped) return null;

                const Icon = step.icon;
                
                return (
                  <div key={step.id} className="flex-1 flex flex-col items-center gap-3 relative">
                    <motion.div 
                      animate={{ 
                        scale: isActive ? 1.1 : 1,
                        borderColor: isActive ? (step.isConditional ? "#eab308" : "#10b981") : isCompleted ? "#10b981" : "rgba(255, 255, 255, 0.1)",
                        backgroundColor: isActive ? (step.isConditional ? "rgba(234, 179, 8, 0.2)" : "rgba(16, 185, 129, 0.2)") : isCompleted ? "rgba(16, 185, 129, 0.1)" : "transparent"
                      }}
                      className={`w-12 h-12 rounded-xl border flex items-center justify-center transition-colors duration-500 ${isActive ? 'glow-emerald' : ''}`}
                    >
                      {isCompleted ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Icon className={`w-6 h-6 ${isActive ? (step.isConditional ? 'text-yellow-400' : 'text-emerald-400') : 'text-slate-600'}`} />
                      )}
                    </motion.div>
                    <span className={`text-[9px] uppercase font-black tracking-tight text-center leading-tight ${isActive ? (step.isConditional ? 'text-yellow-400' : 'text-emerald-400') : 'text-slate-500'}`}>
                      {step.label}
                    </span>
                    
                    {idx < traceSteps.length - 1 && (
                      <div className="absolute top-6 -right-1/2 w-full h-[1px] bg-white/5 -z-10">
                        <motion.div 
                          initial={{ width: "0%" }}
                          animate={{ width: isCompleted ? "100%" : "0%" }}
                          className="h-full bg-emerald-500/30"
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Pruning Performance Visualization */}
      <AnimatePresence>
        {showResults && deltaType !== 'none' && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-4"
          >
            <div className="glass-panel p-6 rounded-3xl border-white/10 overflow-hidden relative">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                    <Filter className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div className="space-y-0.5">
                    <h3 className="text-xs font-black uppercase tracking-widest text-slate-300">Pruning Performance</h3>
                    <p className="text-[10px] text-slate-500 font-bold uppercase tracking-tight">Optimized Document Filtering</p>
                  </div>
                </div>
                <div className="text-right">
                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 font-mono text-[10px]">
                    0.24s (Q-ANSWER)
                  </Badge>
                  <p className="text-[9px] text-slate-600 mt-1 uppercase font-bold tracking-tighter">vs 1.8s Baseline</p>
                </div>
              </div>

              <div className="h-10 w-full flex rounded-xl overflow-hidden bg-slate-900 border border-white/5 shadow-inner">
                <motion.div 
                  initial={{ width: "0%" }}
                  animate={{ width: "99.58%" }}
                  transition={{ duration: 0.8, ease: "circOut" }}
                  className="bg-red-500/15 h-full flex items-center justify-center border-r border-red-500/40 relative overflow-hidden"
                >
                  <div className="absolute inset-0 opacity-10 bg-[repeating-linear-gradient(45deg,transparent,transparent_2px,rgba(239,68,68,0.5)_2px,rgba(239,68,68,0.5)_4px)]" />
                  <span className="text-[9px] font-black text-red-500/60 z-10 tracking-[0.2em] uppercase">9,958 Chunks Pruned</span>
                </motion.div>
                <motion.div 
                  initial={{ width: "0%" }}
                  animate={{ width: "0.42%" }}
                  transition={{ duration: 0.4, delay: 0.8, ease: "easeOut" }}
                  className="bg-emerald-500 h-full shadow-[0_0_25px_rgba(16,185,129,0.4)] z-10 relative"
                >
                  <div className="absolute inset-0 bg-white/20 animate-pulse" />
                </motion.div>
              </div>
              
              <div className="mt-4 flex justify-between items-center text-[10px] font-black uppercase tracking-tighter">
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-1 bg-red-500/30 rounded-full" />
                    <span className="text-slate-500">Unrelated Segments</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-1 bg-emerald-500 rounded-full" />
                    <span className="text-emerald-400">Target Entities (42)</span>
                  </div>
                </div>
                <div className="text-slate-500">
                  Total Corpus: <span className="text-slate-300">10,000 Segments</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results Table */}
      {showResults && (
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel rounded-2xl overflow-hidden border border-white/5 shadow-2xl"
        >
          <div className="px-6 py-4 border-b border-white/10 flex justify-between items-center bg-white/5">
            <div className="flex items-center gap-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-slate-300">Extraction Stage Results</h3>
              {deltaType !== 'none' && (
                <Badge className={`${deltaType === 'row' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' : 'bg-blue-500/10 text-blue-500 border-blue-500/20'} text-[9px] px-2 font-black tracking-widest uppercase`}>
                  {deltaType === 'row' ? 'Delta: Row' : 'Delta: Column'}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
               <Separator orientation="vertical" className="h-4 bg-white/10" />
                <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-[10px] font-mono px-2 h-6">
                  LATENCY: 1.9s
                </Badge>
              </div>
            </div>
          </div>
          <Table>
            <TableHeader className="bg-white/5">
              <TableRow className="hover:bg-transparent border-white/5">
                <TableHead className="text-[10px] uppercase font-black text-slate-500 tracking-widest pl-6">ID</TableHead>
                <TableHead className="text-[10px] uppercase font-black text-slate-500 tracking-widest">Cost</TableHead>
                <TableHead className="text-[10px] uppercase font-black text-slate-500 tracking-widest">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {dummyTables.map((row) => (
                <TableRow key={row.id} className="border-white/5 transition-colors">
                  <TableCell className="font-mono text-xs text-slate-500 pl-6">{row.id}</TableCell>
                  <TableCell 
                    className="cursor-pointer relative group hover:bg-emerald-500/[0.04] transition-colors"
                    onClick={() => onCellClick({ ...row, attribute: 'cost', value: row.cost, sqlContext: sql })}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-slate-200">${row.cost}</span>
                      <MousePointer2 className="w-3 h-3 text-emerald-400/0 group-hover:text-emerald-400/40 transition-all translate-x-1 opacity-0 group-hover:opacity-100" />
                    </div>
                  </TableCell>
                  <TableCell 
                    className="cursor-pointer relative group hover:bg-emerald-500/[0.04] transition-colors"
                    onClick={() => onCellClick({ ...row, attribute: 'status', value: row.status, sqlContext: sql })}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-slate-200">
                        {row.status}
                      </span>
                      <MousePointer2 className="w-3 h-3 text-emerald-400/0 group-hover:text-emerald-400/40 transition-all translate-x-1 opacity-0 group-hover:opacity-100" />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </motion.div>
      )}
    </div>
  );
}
