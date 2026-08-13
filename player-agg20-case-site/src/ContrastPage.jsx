import { useState } from "react";
import data from "./contrast-data.json";
import { DiffBlock, ResultTable, WrongValues } from "./tableViews.jsx";

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
  if (key === "official_accuracy") {
    return record.official_accuracy ?? record.mean_official_accuracy ?? null;
  }
  return record[key]?.[LEVEL] ?? record.rank?.[key]?.[LEVEL] ?? null;
}

function mainScore(record) {
  return metric(record, "query_score");
}

function listOrNone(values) {
  if (!values?.length) return "None";
  return values.join(", ");
}

function Evidence({ system, evidence }) {
  if (!evidence) {
    return <p className="contrast-missing">{system} per-query evidence is not available.</p>;
  }
  const structure = evidence.structure || {};
  const value = evidence.value || {};
  const schema = evidence.schema || {};
  return (
    <div className="contrast-evidence">
      <h4>{system}</h4>
      <dl>
        <div>
          <dt>Key columns</dt>
          <dd>{listOrNone(schema.key_columns)}</dd>
        </div>
        <div>
          <dt>Measure columns</dt>
          <dd>{listOrNone(schema.measure_columns)}</dd>
        </div>
        <div>
          <dt>Missing key columns</dt>
          <dd>{listOrNone(structure.missing_key_columns)}</dd>
        </div>
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
    </div>
  );
}

function QueryCard({ workloadId, query }) {
  const [open, setOpen] = useState(false);
  const metrics = query.metrics || {};
  const evidence = query.evidence || {};
  const schema = query.schema || metrics.quwarts?.schema || metrics.docetl?.schema || {};
  const tables = query.tables || {};
  const differences = query.differences || {};
  const qScore = mainScore(metrics.quwarts) ?? metric(metrics.quwarts, "query_score");
  const dScore = mainScore(metrics.docetl) ?? metric(metrics.docetl, "query_score");
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
            ["QuWARTS", metrics.quwarts],
            ["DocETL", metrics.docetl],
          ].map(([name, record]) => (
            <section key={name} className="contrast-system">
              <h3>{name}</h3>
              <dl>
                <div><dt>Structure</dt><dd>{pct(metric(record, "structure_score"))}</dd></div>
                <div><dt>Cell F1 @20%</dt><dd>{pct(metric(record, "cell_f1"))}</dd></div>
                <div><dt>Main score @20%</dt><dd>{pct(metric(record, "query_score"))}</dd></div>
                <div><dt>UDA-Bench accuracy</dt><dd>{pct(metric(record, "official_accuracy"))}</dd></div>
              </dl>
            </section>
          ))}
        </div>
        <p className="contrast-explanation">{query.explanation}</p>
        <div className="contrast-system-grid">
          <Evidence system="QuWARTS evidence" evidence={evidence.quwarts} />
          <Evidence system="DocETL evidence" evidence={evidence.docetl} />
        </div>
        <div className="tables-grid">
          <div>
            <h3>Ground truth</h3>
            <ResultTable rows={query.gold} schema={schema} emptyLabel="Ground-truth table not attached." />
          </div>
          <div>
            <h3>QuWARTS output</h3>
            <ResultTable
              rows={tables.quwarts}
              schema={schema}
              emptyLabel={tables.quwarts == null ? "Predicted table not in bundle (need serving_bundle)." : "No rows."}
            />
          </div>
          <div>
            <h3>DocETL output</h3>
            <ResultTable
              rows={tables.docetl}
              schema={schema}
              emptyLabel={tables.docetl == null ? "Predicted table not in bundle (need query_tables)." : "No rows."}
            />
          </div>
        </div>
        <div className="diff-grid">
          <div>
            <h3>What QuWARTS got wrong</h3>
            {differences.quwarts ? (
              <>
                <DiffBlock title="Missing groups" rows={differences.quwarts.missing_rows} schema={schema} />
                <DiffBlock title="Extra groups" rows={differences.quwarts.extra_rows} schema={schema} />
                <h5>Wrong values</h5>
                <WrongValues wrong={differences.quwarts.wrong_values} />
              </>
            ) : (
              <p className="empty">Diff unavailable until QuWARTS predicted rows are harvested.</p>
            )}
          </div>
          <div>
            <h3>What DocETL got wrong</h3>
            {differences.docetl ? (
              <>
                <DiffBlock title="Missing groups" rows={differences.docetl.missing_rows} schema={schema} />
                <DiffBlock title="Extra groups" rows={differences.docetl.extra_rows} schema={schema} />
                <h5>Wrong values</h5>
                <WrongValues wrong={differences.docetl.wrong_values} />
              </>
            ) : (
              <p className="empty">Diff unavailable until DocETL predicted rows are harvested.</p>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

export default function ContrastPage() {
  const workloads = Object.entries(data.workloads || {});
  const qTokens = workloads.reduce((sum, [, row]) => {
    const value = row.quwarts?.tokens_actual;
    return value == null ? sum : (sum ?? 0) + Number(value);
  }, null);
  const dTokens = workloads.reduce((sum, [, row]) => {
    const value = row.docetl?.tokens_actual;
    return value == null ? sum : (sum ?? 0) + Number(value);
  }, null);
  return (
    <div className="page contrast-page">
      <div className="atmosphere" aria-hidden="true" />
      <header className="contrast-hero">
        <p className="eyebrow">Four workloads · {data.query_count} queries</p>
        <h1>Player contrast results</h1>
        <p className="lede">
          {data.subtitle}. Main score is structure F2 × cell F1 at 20% relative error. Official
          UDA-Bench accuracy is shown only as a reference metric.
        </p>
        {!data.per_query_metrics_complete ? (
          <p className="contrast-notice">This local bundle uses audited aggregate results. Query SQL and descriptions are complete; per-query system metrics will appear after the strict HPC harvest.</p>
        ) : null}
        {data.tables_attached && !data.tables_complete ? (
          <p className="contrast-notice">
            Ground-truth tables are attached. Predicted QuWARTS/DocETL tables (and therefore missing/extra groups) appear after the result directories include `serving_bundle` and `query_tables` next to each `evaluation.json`.
          </p>
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
          <p>
            Aggregate cards compare structure F2, cell F1 @20%, and the main score (structure ×
            cell F1). Official UDA-Bench accuracy is listed separately and is not the ranking
            score. Expanded queries show ground truth, system outputs, missing groups, extra
            groups, and wrong values when those tables are harvested.
          </p>
          <p>
            Taxonomy lineage and cross-workload transfer are on the{" "}
            <a href="/experiments">experiments page</a>.
            Gold, predicted, missing-group, extra-group, and wrong-value tables stay on this page.
          </p>
        </section>
        {workloads.map(([workloadId, row]) => {
          const q = row.quwarts?.scores || {};
          const d = row.docetl?.scores || {};
          const queries = row.queries || [];
          return (
            <section className="contrast-workload" key={workloadId} id={workloadId}>
              <header>
                <div><p className="eyebrow">{row.focus}</p><h2>{workloadId}</h2></div>
                <p>{row.explanation}</p>
              </header>
              <div className="contrast-aggregate-grid">
                {[
                  ["QuWARTS", q, row.quwarts?.tokens_actual],
                  ["DocETL", d, row.docetl?.tokens_actual],
                ].map(([name, scores, tokenCount]) => (
                  <article key={name}>
                    <h3>{name}</h3>
                    <dl>
                      <div><dt>Structure</dt><dd>{pct(scores.mean_structure_score)}</dd></div>
                      <div><dt>Cell F1 @20%</dt><dd>{pct(scores.mean_cell_f1?.[LEVEL])}</dd></div>
                      <div><dt>Main score @20%</dt><dd>{pct(scores.mean_query_score?.[LEVEL])}</dd></div>
                      <div><dt>UDA-Bench accuracy</dt><dd>{pct(scores.mean_official_accuracy)}</dd></div>
                      <div><dt>Tokens</dt><dd>{tokens(tokenCount)}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
              <div className="contrast-query-list">
                {queries.map((query) => <QueryCard key={query.query_id} workloadId={workloadId} query={query} />)}
              </div>
            </section>
          );
        })}
      </main>
      <footer className="footer">Generated from validated workload manifests and evaluation artifacts.</footer>
    </div>
  );
}
