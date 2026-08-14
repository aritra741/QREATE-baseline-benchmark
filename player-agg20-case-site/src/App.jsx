import { useMemo, useState } from "react";
import CommentsSystem from "./Comments.jsx";
import ContrastPage from "./ContrastPage.jsx";
import ExperimentsPage from "./ExperimentsPage.jsx";
import caseStudyNarratives from "./case-study-narratives.json";
import data from "./data.json";
import { DiffBlock, ResultTable, WrongValues } from "./tableViews.jsx";

const PRIMARY_LEVEL = data.primary_error_level || "0.2";

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatTokens(value) {
  return Number(value).toLocaleString("en-US");
}

function questionLabel(queryId) {
  const index = Number(String(queryId).replace(/\D+/g, ""));
  return Number.isFinite(index) ? `Question ${index + 1}` : "Question";
}

function mainScore(systemScores, level = PRIMARY_LEVEL) {
  return systemScores?.query_score?.[level] ?? 0;
}

function ScoreChip({ label, value, tone }) {
  return (
    <span className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{pct(value)}</span>
    </span>
  );
}

function QuestionCaseStudy({ queryId }) {
  const narrative = caseStudyNarratives[queryId];
  if (!narrative) return null;
  return (
    <article className="question-case-study" aria-label="Question analysis">
      {narrative.paragraphs.map((paragraph) => (
        <p key={paragraph}>{paragraph}</p>
      ))}
    </article>
  );
}

function SystemScoreCard({ title, scores }) {
  return (
    <div className="score-card">
      <h3>{title}</h3>
      <dl className="score-meta">
        <div>
          <dt>Structure</dt>
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
              <th>Structure</th>
              <th>Official accuracy</th>
              <th>Score at 20% error</th>
            </tr>
          </thead>
          <tbody>
            <tr className="primary-level">
              <td>{pct(scores.structure_f2)}</td>
              <td>{pct(scores.official_accuracy)}</td>
              <td>{pct(scores.query_score[PRIMARY_LEVEL])}</td>
            </tr>
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
          <ScoreChip label="QuWARTS structure" value={q.structure_f2} tone="quwarts" />
          <ScoreChip label="QuWARTS score" value={qMain} tone="quwarts" />
          <ScoreChip label="DocETL structure" value={d.structure_f2} tone="docetl" />
          <ScoreChip label="DocETL score" value={dMain} tone="docetl" />
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

        <QuestionCaseStudy queryId={query.query_id} />
      </div>
    </section>
  );
}

function currentPath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

function SiteNav() {
  const path = currentPath();
  return (
    <nav className="site-nav" aria-label="Case study pages">
      <a href="/" className={path === "/" ? "active" : ""}>Case study</a>
      <a href="/contrasts" className={path === "/contrasts" ? "active" : ""}>Results</a>
      <a href="/experiments" className={path === "/experiments" ? "active" : ""}>Transfer</a>
    </nav>
  );
}

function CaseStudyPage() {
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
          <h1>{data.title}</h1>
          <p className="lede">
            Compare QuWARTS and DocETL on 20 Player questions. Open a question to see the ground
            truth, both answers, and what went wrong. Select any text to leave a comment.
          </p>
          <p className="paper-note">
            DocETL claims are cited to the relevant section of{" "}
            <a href={data.paper.url} target="_blank" rel="noreferrer">
              the DocETL paper
            </a>
            ; runner-specific behavior is identified separately.
          </p>
          <div className="hero-metrics">
            <div>
              <span className="metric-label">QuWARTS structure</span>
              <strong>{pct(data.means.quwarts.structure_f2)}</strong>
            </div>
            <div>
              <span className="metric-label">DocETL structure</span>
              <strong>{pct(data.means.docetl.structure_f2)}</strong>
            </div>
            <div>
              <span className="metric-label">QuWARTS official accuracy</span>
              <strong>{pct(data.means.quwarts.official_accuracy)}</strong>
            </div>
            <div>
              <span className="metric-label">DocETL official accuracy</span>
              <strong>{pct(data.means.docetl.official_accuracy)}</strong>
            </div>
            <div>
              <span className="metric-label">QuWARTS score</span>
              <strong>{pct(data.means.quwarts.query_score["0.2"])}</strong>
            </div>
            <div>
              <span className="metric-label">DocETL score</span>
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
            Open a question to see where each system missed a group, added a group, or got a value
            wrong.
          </p>
        </footer>
      </div>
  );
}

export default function App() {
  const path = currentPath();
  const page =
    path === "/contrasts" ? (
      <ContrastPage />
    ) : path === "/experiments" ? (
      <ExperimentsPage />
    ) : (
      <CaseStudyPage />
    );
  return (
    <CommentsSystem>
      <SiteNav />
      {page}
    </CommentsSystem>
  );
}
