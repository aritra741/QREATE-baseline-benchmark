export interface SystemMetrics {
  preprocessingTime: string;
  runtime: number; // in seconds
  tokensUsed: number;
  precision: number;
  recall: number;
  f1: number;
  matchingRows: number;
  rowsInSystemNotGT: number;
  rowsInGTNotSystem: number;
}

export interface System {
  id: string;
  name: string;
  color: string;
  isGT?: boolean;
}

export interface QueryResult {
  queryId: string;
  metrics: Record<string, SystemMetrics>; // systemId -> metrics
  results: Record<string, any[]>; // systemId -> results
}
