import { useMemo, useState } from "react";
import data from "./data.json";

const ERROR_LEVELS = data.error_levels || ["0.01", "0.05", "0.2"];
const PRIMARY_LEVEL = data.primary_error_level || "0.2";

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatTokens(value) {
  return Number(value).toLocaleString("en-US");
}

function errorLabel(level) {
  return `${Math.round(Number(level) * 100)}% error`;
}

function questionLabel(queryId) {
  const index = Number(String(queryId).replace(/\D+/g, ""));
  return Number.isFinite(index) ? `Question ${index + 1}` : "Question";
}

function mainScore(systemScores, level = PRIMARY_LEVEL) {
  return systemScores?.query_score?.[level] ?? 0;
}

function fmtCell(value) {
  if (value == null || value === "") return "∅";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    return Number.isInteger(value) ? String(value) : value.toPrecision(6).replace(/\.?0+$/, "");
  }
  const text = String(value);
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}

function columnsFromRows(rows, schema) {
  if (schema?.key_columns?.length || schema?.measure_columns?.length) {
    return [...(schema.key_columns || []), ...(schema.measure_columns || [])];
  }
  if (!rows?.length) return [];
  return Object.keys(rows[0]);
}

function ScoreChip({ label, value, tone }) {
  return (
    <span className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{pct(value)}</span>
    </span>
  );
}

function ResultTable({ rows, schema, emptyLabel }) {
  const columns = columnsFromRows(rows, schema);
  if (!rows?.length) {
    return <p className="empty">{emptyLabel || "No rows."}</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column} title={String(row[column] ?? "")}>
                  {fmtCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiffBlock({ title, rows, schema }) {
  return (
    <div className="diff-block">
      <h5>{title}</h5>
      <ResultTable rows={rows} schema={schema} emptyLabel="None." />
    </div>
  );
}

function WrongValues({ wrong }) {
  if (!wrong?.length) return <p className="empty">None.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>group</th>
            <th>measure</th>
            <th>gold</th>
            <th>predicted</th>
          </tr>
        </thead>
        <tbody>
          {wrong.flatMap((row, i) =>
            Object.entries(row.differences).map(([measure, values]) => (
              <tr key={`${i}-${measure}`}>
                <td>
                  {Object.entries(row.key)
                    .map(([k, v]) => `${k}=${fmtCell(v)}`)
                    .join(", ")}
                </td>
                <td>{measure}</td>
                <td>{fmtCell(values.gold)}</td>
                <td>{fmtCell(values.predicted)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function ReasonPanel({ system, reason }) {
  if (!reason) return null;
  return (
    <article className={`reason reason-${system}`}>
      <header>
        <h4>{system === "quwarts" ? "QuWARTS" : "DocETL"} system analysis</h4>
      </header>
      <dl className="analysis-list">
        <div>
          <dt>Pipeline stage</dt>
          <dd>{reason.component}</dd>
        </div>
        <div>
          <dt>Root cause</dt>
          <dd>{reason.root_cause}</dd>
        </div>
        <div>
          <dt>Pipeline behavior behind it</dt>
          <dd>{reason.design_choice}</dd>
        </div>
        <div>
          <dt>Why validation allowed it</dt>
          <dd>{reason.why_checks_missed}</dd>
        </div>
        <div>
          <dt>How it affected the result</dt>
          <dd>{reason.failure_path}</dd>
        </div>
      </dl>
      <h5>What I found in the final and working tables</h5>
      <ul>
        {(reason.evidence || []).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}

function SystemScoreCard({ title, scores }) {
  return (
    <div className="score-card">
      <h3>{title}</h3>
      <p className="score-formula">Main score = structure F2 × cell accuracy</p>
      <dl className="score-meta">
        <div>
          <dt>Structure F2</dt>
          <dd>{pct(scores.structure_f2)}</dd>
        </div>
        <div>
          <dt>Rows</dt>
          <dd>
            {scores.pred_rows} out of {scores.gold_rows}
          </dd>
        </div>
      </dl>
      <div className="score-table-wrap">
        <table className="score-table">
          <thead>
            <tr>
              <th>Error level</th>
              <th>Structure F2</th>
              <th>Cell accuracy</th>
              <th>Main score</th>
            </tr>
          </thead>
          <tbody>
            {ERROR_LEVELS.map((level) => (
              <tr key={level} className={level === PRIMARY_LEVEL ? "primary-level" : ""}>
                <td>{errorLabel(level)}</td>
                <td>{pct(scores.structure_f2)}</td>
                <td>{pct(scores.cell_f1[level])}</td>
                <td>{pct(scores.query_score[level])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QueryPanel({ query, open, onToggle }) {
  const q = query.scores.quwarts;
  const d = query.scores.docetl;
  const qMain = mainScore(q);
  const dMain = mainScore(d);
  const winner = qMain === dMain ? "tie" : qMain > dMain ? "quwarts" : "docetl";

  return (
    <section className={`query ${open ? "open" : ""}`} id={query.query_id}>
      <button type="button" className="query-head" onClick={onToggle} aria-expanded={open}>
        <div className="query-id-block">
          <span className="query-id">{questionLabel(query.query_id)}</span>
          <span className={`winner winner-${winner}`}>
            {winner === "tie" ? "tie" : winner === "quwarts" ? "QuWARTS" : "DocETL"}
          </span>
        </div>
        <p className="query-nl">{query.nl}</p>
        <div className="query-scores">
          <ScoreChip label="QuWARTS F2" value={q.structure_f2} tone="quwarts" />
          <ScoreChip label={`QuWARTS @20%`} value={qMain} tone="quwarts" />
          <ScoreChip label="DocETL F2" value={d.structure_f2} tone="docetl" />
          <ScoreChip label={`DocETL @20%`} value={dMain} tone="docetl" />
          <span className="chevron" aria-hidden="true" />
        </div>
      </button>

      <div className="query-body" hidden={!open}>
        <div className="sql-block">
          <h3>Query</h3>
          <pre>{query.reference_sql}</pre>
        </div>

        <div className="score-grid">
          <SystemScoreCard title="QuWARTS scores" scores={q} />
          <SystemScoreCard title="DocETL scores" scores={d} />
        </div>

        <div className="tables-grid">
          <div>
            <h3>Ground truth</h3>
            <ResultTable rows={query.gold} schema={query.schema} />
          </div>
          <div>
            <h3>QuWARTS output</h3>
            <ResultTable rows={query.quwarts} schema={query.schema} />
          </div>
          <div>
            <h3>DocETL output</h3>
            <ResultTable rows={query.docetl} schema={query.schema} />
          </div>
        </div>

        <div className="diff-grid">
          <div>
            <h3>What QuWARTS got wrong</h3>
            <DiffBlock
              title="Missing groups"
              rows={query.differences.quwarts.missing_rows}
              schema={query.schema}
            />
            <DiffBlock
              title="Extra groups"
              rows={query.differences.quwarts.extra_rows}
              schema={query.schema}
            />
            <h5>Wrong values</h5>
            <WrongValues wrong={query.differences.quwarts.wrong_values} />
          </div>
          <div>
            <h3>What DocETL got wrong</h3>
            <DiffBlock
              title="Missing groups"
              rows={query.differences.docetl.missing_rows}
              schema={query.schema}
            />
            <DiffBlock
              title="Extra groups"
              rows={query.differences.docetl.extra_rows}
              schema={query.schema}
            />
            <h5>Wrong values</h5>
            <WrongValues wrong={query.differences.docetl.wrong_values} />
          </div>
        </div>

        <div className="reasons">
          <ReasonPanel system="quwarts" reason={query.reasons.quwarts} />
          <ReasonPanel system="docetl" reason={query.reasons.docetl} />
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [openId, setOpenId] = useState("q0");
  const [filter, setFilter] = useState("all");

  const queries = useMemo(() => {
    return data.queries.filter((query) => {
      if (filter === "all") return true;
      const q = mainScore(query.scores.quwarts);
      const d = mainScore(query.scores.docetl);
      if (filter === "quwarts") return q > d;
      if (filter === "docetl") return d > q;
      if (filter === "zero") return q === 0 && d === 0;
      return true;
    });
  }, [filter]);

  return (
    <div className="page">
      <div className="atmosphere" aria-hidden="true" />
      <header className="hero">
        <h1>QuWARTS case study Aug 6, 2026</h1>
        <p className="lede">
          Compare QuWARTS and DocETL on 20 Player questions. The main score is structure F2 times
          cell accuracy, shown at 1%, 5%, and 20% error. Open a question to see the ground truth,
          both answers, and a plain explanation of what went wrong.
        </p>
        <div className="hero-metrics">
          <div>
            <span className="metric-label">QuWARTS structure F2</span>
            <strong>{pct(data.means.quwarts.structure_f2)}</strong>
          </div>
          <div>
            <span className="metric-label">DocETL structure F2</span>
            <strong>{pct(data.means.docetl.structure_f2)}</strong>
          </div>
          <div>
            <span className="metric-label">QuWARTS main score @20% error</span>
            <strong>{pct(data.means.quwarts.query_score["0.2"])}</strong>
          </div>
          <div>
            <span className="metric-label">DocETL main score @20% error</span>
            <strong>{pct(data.means.docetl.query_score["0.2"])}</strong>
          </div>
          <div>
            <span className="metric-label">Total tokens</span>
            <strong>{formatTokens(data.tokens.total)}</strong>
          </div>
        </div>
        <div className="token-breakdown">
          <span>QuWARTS {formatTokens(data.tokens.quwarts)} tokens</span>
          <span>DocETL {formatTokens(data.tokens.docetl)} tokens</span>
        </div>
        <a className="cta" href="#queries">
          See the questions
        </a>
      </header>

      <main id="queries" className="main">
        <div className="toolbar">
          <h2>Questions</h2>
          <div className="filters" role="tablist" aria-label="Filter questions">
            {[
              ["all", "All"],
              ["quwarts", "QuWARTS better"],
              ["docetl", "DocETL better"],
              ["zero", "Both scored 0"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={filter === id ? "active" : ""}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="query-list">
          {queries.map((query) => (
            <QueryPanel
              key={query.query_id}
              query={query}
              open={openId === query.query_id}
              onToggle={() =>
                setOpenId((current) => (current === query.query_id ? null : query.query_id))
              }
            />
          ))}
        </div>
      </main>

      <footer className="footer">
        <p>
          Built from the QuWARTS and DocETL Player runs. Open a question to see where each system
          missed a group, added a group, or got a value wrong, and why.
        </p>
      </footer>
    </div>
  );
}
