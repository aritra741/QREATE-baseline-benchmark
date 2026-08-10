import { useState } from "react";
import data from "./contrast-data.json";

const LEVEL = data.primary_error_level || "0.2";

function pct(value) {
  return value == null ? "Not available" : `${(Number(value) * 100).toFixed(1)}%`;
}

function tokens(value) {
  return value == null ? "Not reported" : Number(value).toLocaleString("en-US");
}

function metric(record, key) {
  if (!record) return null;
  if (key === "structure_score") return record.structure_score ?? record.rank?.structure_score;
  return record[key]?.[LEVEL] ?? record.rank?.[key]?.[LEVEL] ?? null;
}

function Evidence({ system, evidence }) {
  if (!evidence) {
    return <p className="contrast-missing">{system} per-query evidence is not available.</p>;
  }
  const structure = evidence.structure || {};
  const value = evidence.value || {};
  return (
    <div className="contrast-evidence">
      <h4>{system}</h4>
      <dl>
        <div>
          <dt>Rows</dt>
          <dd>
            {evidence.predicted_row_count ?? "?"} predicted / {evidence.gold_row_count ?? "?"} gold
          </dd>
        </div>
        <div>
          <dt>Key alignment</dt>
          <dd>{structure.key_alignment_failed == null ? "Not reported" : structure.key_alignment_failed ? "Failed" : "Passed"}</dd>
        </div>
        <div>
          <dt>Row recall context</dt>
          <dd>{pct(value.row_recall_context)}</dd>
        </div>
      </dl>
      {structure.missing_key_columns?.length ? (
        <p>Missing key columns: {structure.missing_key_columns.join(", ")}</p>
      ) : null}
    </div>
  );
}

function QueryCard({ workloadId, query }) {
  const [open, setOpen] = useState(false);
  const qScore = metric(query.metrics.quwarts, "query_score");
  const dScore = metric(query.metrics.docetl, "query_score");
  const winner =
    qScore == null || dScore == null
      ? "Awaiting detailed metrics"
      : qScore === dScore
        ? "Tie"
        : qScore > dScore
          ? "QuWARTS"
          : "DocETL";
  return (
    <article className="contrast-query">
      <button type="button" className="contrast-query-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="contrast-query-id">{workloadId} · {query.query_id}</span>
        <span>{query.text}</span>
        <strong>{winner}</strong>
      </button>
      <div hidden={!open} className="contrast-query-body">
        <pre>{query.sql}</pre>
        <div className="contrast-system-grid">
          {[
            ["QuWARTS", query.metrics.quwarts],
            ["DocETL", query.metrics.docetl],
          ].map(([name, record]) => (
            <section key={name} className="contrast-system">
              <h3>{name}</h3>
              <dl>
                <div><dt>Structure</dt><dd>{pct(metric(record, "structure_score"))}</dd></div>
                <div><dt>Cell F1 @20%</dt><dd>{pct(metric(record, "cell_f1"))}</dd></div>
                <div><dt>Query score @20%</dt><dd>{pct(metric(record, "query_score"))}</dd></div>
              </dl>
            </section>
          ))}
        </div>
        <p className="contrast-explanation">{query.explanation}</p>
        <div className="contrast-system-grid">
          <Evidence system="QuWARTS evidence" evidence={query.evidence.quwarts} />
          <Evidence system="DocETL evidence" evidence={query.evidence.docetl} />
        </div>
      </div>
    </article>
  );
}

export default function ContrastPage() {
  const workloads = Object.entries(data.workloads);
  const qTokens = workloads.reduce((sum, [, row]) => sum + Number(row.quwarts.tokens_actual || 0), 0);
  const dTokens = workloads.reduce((sum, [, row]) => sum + Number(row.docetl.tokens_actual || 0), 0);
  return (
    <div className="page contrast-page">
      <div className="atmosphere" aria-hidden="true" />
      <header className="contrast-hero">
        <p className="eyebrow">Four workloads · {data.query_count} queries</p>
        <h1>Player contrast results</h1>
        <p className="lede">{data.subtitle}. {data.score_note}</p>
        {!data.per_query_metrics_complete ? (
          <p className="contrast-notice">This local bundle uses audited aggregate results. Query SQL and descriptions are complete; per-query system metrics will appear after the strict HPC harvest.</p>
        ) : null}
      </header>
      <main>
        <section className="contrast-token-summary">
          <div><span>QuWARTS tokens</span><strong>{tokens(qTokens)}</strong></div>
          <div><span>DocETL tokens</span><strong>{tokens(dTokens)}</strong></div>
          <div><span>QuWARTS token share</span><strong>{dTokens ? pct(qTokens / dTokens) : "Not available"}</strong></div>
        </section>
        <section className="contrast-method">
          <h2>Methodology</h2>
          <p>Aggregate cards compare official accuracy, structure score, and the structure × cell-F1 query score at 20% relative-error tolerance. Explanations state only differences present in the harvested metrics and evidence.</p>
        </section>
        {workloads.map(([workloadId, row]) => {
          const q = row.quwarts.scores;
          const d = row.docetl.scores;
          return (
            <section className="contrast-workload" key={workloadId} id={workloadId}>
              <header>
                <div><p className="eyebrow">{row.focus}</p><h2>{workloadId}</h2></div>
                <p>{row.explanation}</p>
              </header>
              <div className="contrast-aggregate-grid">
                {[
                  ["QuWARTS", q, row.quwarts.tokens_actual],
                  ["DocETL", d, row.docetl.tokens_actual],
                ].map(([name, scores, tokenCount]) => (
                  <article key={name}>
                    <h3>{name}</h3>
                    <dl>
                      <div><dt>Official accuracy</dt><dd>{pct(scores.mean_official_accuracy)}</dd></div>
                      <div><dt>Structure</dt><dd>{pct(scores.mean_structure_score)}</dd></div>
                      <div><dt>Query score @20%</dt><dd>{pct(scores.mean_query_score?.[LEVEL])}</dd></div>
                      <div><dt>Tokens</dt><dd>{tokens(tokenCount)}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
              <div className="contrast-query-list">
                {row.queries.map((query) => <QueryCard key={query.query_id} workloadId={workloadId} query={query} />)}
              </div>
            </section>
          );
        })}
      </main>
      <footer className="footer">Generated from validated workload manifests and evaluation artifacts.</footer>
    </div>
  );
}
