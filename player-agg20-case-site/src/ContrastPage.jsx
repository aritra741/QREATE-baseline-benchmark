import { useState } from "react";
import data from "./contrast-data.json";
import { variantLabel, variantTables } from "./queryProperties.js";
import { DiffBlock, ResultTable, WrongValues } from "./tableViews.jsx";

const LEVEL = data.primary_error_level || "0.2";

const NAMES = {
  player_join20: { title: "Joins", blurb: "Questions that join across tables." },
  player_groupby20: { title: "Group by", blurb: "Questions that group rows and summarize them." },
  player_multiagg20: { title: "Aggregates", blurb: "Questions with several aggregates." },
  player_filterjoin20: { title: "Filters", blurb: "Questions that filter, with some joins." },
};

function pct(value) {
  return value == null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
}

function tokens(value) {
  return value == null ? "—" : Number(value).toLocaleString("en-US");
}

function metric(record, key) {
  if (!record) return null;
  if (key === "structure_score") return record.structure_score ?? record.rank?.structure_score;
  return record[key]?.[LEVEL] ?? record.rank?.[key]?.[LEVEL] ?? null;
}

function mainScore(record) {
  return metric(record, "query_score");
}

function mean(values) {
  const nums = values.filter((value) => value != null && !Number.isNaN(Number(value))).map(Number);
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

function systemMeans(queries, system) {
  return {
    score: mean(queries.map((query) => mainScore(query.metrics?.[system]))),
    structure: mean(queries.map((query) => metric(query.metrics?.[system], "structure_score"))),
    accuracy: mean(queries.map((query) => metric(query.metrics?.[system], "cell_f1"))),
  };
}

function leadClass(self, other) {
  if (self == null || other == null) return "";
  const a = Number(self);
  const b = Number(other);
  if (Number.isNaN(a) || Number.isNaN(b) || a < b) return "";
  return "cell-lead";
}

function VariantTables({ workloadId, queries }) {
  const tables = variantTables(workloadId, queries);
  if (!tables.length) return null;
  return (
    <div className="variant-block">
      {tables.map((table) => (
        <section key={table.title} className="variant-table">
          <h3>{table.title}</h3>
          <div className="exp-table-wrap">
            <table className="exp-table">
              <thead>
                <tr>
                  <th>Variation</th>
                  <th className="num">Questions</th>
                  <th className="num">QuWARTS structure</th>
                  <th className="num">QuWARTS accuracy</th>
                  <th className="num">QuWARTS score</th>
                  <th className="num">DocETL structure</th>
                  <th className="num">DocETL accuracy</th>
                  <th className="num">DocETL score</th>
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => {
                  const q = systemMeans(row.queries, "quwarts");
                  const d = systemMeans(row.queries, "docetl");
                  return (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td className="num">{row.queries.length}</td>
                      <td className={`num ${leadClass(q.structure, d.structure)}`}>{pct(q.structure)}</td>
                      <td className={`num ${leadClass(q.accuracy, d.accuracy)}`}>{pct(q.accuracy)}</td>
                      <td className={`num ${leadClass(q.score, d.score)}`}>{pct(q.score)}</td>
                      <td className={`num ${leadClass(d.structure, q.structure)}`}>{pct(d.structure)}</td>
                      <td className={`num ${leadClass(d.accuracy, q.accuracy)}`}>{pct(d.accuracy)}</td>
                      <td className={`num ${leadClass(d.score, q.score)}`}>{pct(d.score)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function QueryCard({ workloadId, query }) {
  const [open, setOpen] = useState(false);
  const metrics = query.metrics || {};
  const schema = query.schema || metrics.quwarts?.schema || metrics.docetl?.schema || {};
  const tables = query.tables || {};
  const differences = query.differences || {};
  const qScore = mainScore(metrics.quwarts);
  const dScore = mainScore(metrics.docetl);
  const winner =
    qScore == null || dScore == null
      ? "—"
      : qScore === dScore
        ? "Tie"
        : qScore > dScore
          ? "QuWARTS"
          : "DocETL";
  return (
    <article className="contrast-query">
      <button type="button" className="contrast-query-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="contrast-query-id">{NAMES[workloadId]?.title || workloadId} · {query.query_id} · {variantLabel(workloadId, query.sql)}</span>
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
                <div><dt>Score</dt><dd>{pct(metric(record, "query_score"))}</dd></div>
                <div><dt>Structure</dt><dd>{pct(metric(record, "structure_score"))}</dd></div>
                <div><dt>Accuracy</dt><dd>{pct(metric(record, "cell_f1"))}</dd></div>
              </dl>
            </section>
          ))}
        </div>
        <div className="tables-grid">
          <div>
            <h3>Ground truth</h3>
            <ResultTable rows={query.gold} schema={schema} emptyLabel="No table." />
          </div>
          <div>
            <h3>QuWARTS</h3>
            <ResultTable
              rows={tables.quwarts}
              schema={schema}
              emptyLabel={tables.quwarts == null ? "No table." : "No rows."}
            />
          </div>
          <div>
            <h3>DocETL</h3>
            <ResultTable
              rows={tables.docetl}
              schema={schema}
              emptyLabel={tables.docetl == null ? "No table." : "No rows."}
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
              <p className="empty">No comparison table.</p>
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
              <p className="empty">No comparison table.</p>
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
        <p className="eyebrow">80 questions</p>
        <h1>Results</h1>
        <p className="lede">
          QuWARTS vs DocETL on four sets of Player questions: joins, group by, aggregates, and
          filters. Open a question to see both answers.
        </p>
      </header>
      <main>
        <section className="contrast-token-summary">
          <div><span>QuWARTS tokens</span><strong>{tokens(qTokens)}</strong></div>
          <div><span>DocETL tokens</span><strong>{tokens(dTokens)}</strong></div>
          <div><span>QuWARTS share</span><strong>{dTokens ? pct(qTokens / dTokens) : "—"}</strong></div>
        </section>
        {workloads.map(([workloadId, row]) => {
          const q = row.quwarts?.scores || {};
          const d = row.docetl?.scores || {};
          const queries = row.queries || [];
          const names = NAMES[workloadId] || { title: workloadId, blurb: "" };
          return (
            <section className="contrast-workload" key={workloadId} id={workloadId}>
              <header>
                <div>
                  <p className="eyebrow">{queries.length} questions</p>
                  <h2>{names.title}</h2>
                </div>
                <p>{names.blurb}</p>
              </header>
              <div className="contrast-aggregate-grid">
                {[
                  ["QuWARTS", q, row.quwarts?.tokens_actual],
                  ["DocETL", d, row.docetl?.tokens_actual],
                ].map(([name, scores, tokenCount]) => (
                  <article key={name}>
                    <h3>{name}</h3>
                    <dl>
                      <div><dt>Score</dt><dd>{pct(scores.mean_query_score?.[LEVEL])}</dd></div>
                      <div><dt>Structure</dt><dd>{pct(scores.mean_structure_score)}</dd></div>
                      <div><dt>Accuracy</dt><dd>{pct(scores.mean_cell_f1?.[LEVEL])}</dd></div>
                      <div><dt>Tokens</dt><dd>{tokens(tokenCount)}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
              <VariantTables workloadId={workloadId} queries={queries} />
              <div className="contrast-query-list">
                {queries.map((query) => <QueryCard key={query.query_id} workloadId={workloadId} query={query} />)}
              </div>
            </section>
          );
        })}
      </main>
    </div>
  );
}
