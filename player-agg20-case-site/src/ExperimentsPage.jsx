import data from "./experiments-data.json";

const NAMES = {
  player_join20: "Joins",
  player_groupby20: "Group by",
  player_multiagg20: "Aggregates",
  player_filterjoin20: "Filters",
};

const WORKLOADS = data.workloads || [];

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function tokens(value) {
  if (value == null) return "—";
  return Number(value).toLocaleString("en-US");
}

function score(row) {
  if (row?.query_score != null) return Number(row.query_score);
  if (row?.structure == null || row?.cell_f1 == null) return null;
  return Number(row.structure) * Number(row.cell_f1);
}

function deltaClass(value) {
  if (value == null || Number.isNaN(Number(value)) || value === 0) return "";
  return Number(value) > 0 ? "delta-pos" : "delta-neg";
}

function signedPct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value) * 100;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)} pp`;
}

function shortName(workloadId) {
  return NAMES[workloadId] || WORKLOADS.find((row) => row.id === workloadId)?.short || workloadId;
}

function ScoreTable({ columns, rows }) {
  return (
    <div className="exp-table-wrap">
      <table className="exp-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.numeric ? "num" : ""}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`${column.numeric ? "num" : ""} ${column.className?.(row) || ""}`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonSection() {
  const rows = data.contrast_25pct.rows.map((row) => {
    const qScore = score(row.quwarts);
    const dScore = score(row.docetl);
    return {
      key: row.workload_id,
      ...row,
      qScore,
      dScore,
      delta: qScore - dScore,
    };
  });
  return (
    <section className="exp-section" id="comparison">
      <h2>QuWARTS vs DocETL</h2>
      <p>QuWARTS used about a quarter of the tokens and scored higher on every set of questions.</p>
      <ScoreTable
        columns={[
          { key: "w", label: "Questions", render: (row) => shortName(row.workload_id) },
          { key: "qs", label: "QuWARTS score", numeric: true, render: (row) => pct(row.qScore) },
          { key: "ds", label: "DocETL score", numeric: true, render: (row) => pct(row.dScore) },
          {
            key: "delta",
            label: "Difference",
            numeric: true,
            className: (row) => deltaClass(row.delta),
            render: (row) => signedPct(row.delta),
          },
          { key: "qst", label: "QuWARTS structure", numeric: true, render: (row) => pct(row.quwarts.structure) },
          { key: "dst", label: "DocETL structure", numeric: true, render: (row) => pct(row.docetl.structure) },
          { key: "qa", label: "QuWARTS accuracy", numeric: true, render: (row) => pct(row.quwarts.accuracy) },
          { key: "da", label: "DocETL accuracy", numeric: true, render: (row) => pct(row.docetl.accuracy) },
          { key: "qt", label: "QuWARTS tokens", numeric: true, render: (row) => tokens(row.quwarts.tokens) },
          { key: "dt", label: "DocETL tokens", numeric: true, render: (row) => tokens(row.docetl.tokens) },
        ]}
        rows={rows}
      />
    </section>
  );
}

function TransferSection() {
  const ids = WORKLOADS.map((row) => row.id);
  const inWorkload = Object.fromEntries(
    data.contrast_25pct.rows.map((row) => [
      row.workload_id,
      {
        accuracy: row.quwarts.accuracy,
        structure: row.quwarts.structure,
        query_score: row.quwarts.query_score,
        kind: "same",
      },
    ])
  );
  const transferred = {};
  for (const pair of data.cross_eval.pairs || []) {
    transferred[`${pair.train}:${pair.test}`] = pair;
  }

  function cell(train, test) {
    if (train === test) return inWorkload[train];
    return transferred[`${train}:${test}`] || { kind: "pending" };
  }

  return (
    <section className="exp-section" id="transfer">
      <h2>Asking one set of questions on a database built for another</h2>
      <p>
        Each row is a database built from one set of questions. Each column is a set of questions
        asked against that database. The highlighted diagonal is the matching pair.
      </p>
      <div className="exp-table-wrap">
        <table className="exp-table exp-matrix">
          <thead>
            <tr>
              <th>Database from ↓ / questions →</th>
              {ids.map((id) => (
                <th key={id} className="num">
                  {shortName(id)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ids.map((train) => (
              <tr key={train}>
                <th>{shortName(train)}</th>
                {ids.map((test) => {
                  const value = cell(train, test);
                  const pending = value.kind === "pending";
                  return (
                    <td
                      key={test}
                      className={`num ${train === test ? "matrix-diag" : ""} ${pending ? "matrix-pending" : ""}`}
                    >
                      {pending ? (
                        <span>—</span>
                      ) : (
                        <>
                          <strong>{pct(score(value))}</strong>
                          <small>
                            {pct(value.accuracy)} accuracy · {pct(value.structure)} structure
                          </small>
                        </>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(data.cross_eval.pairs || []).length > 0 ? (
        <ScoreTable
          columns={[
            { key: "tr", label: "Database from", render: (row) => shortName(row.train) },
            { key: "te", label: "Questions", render: (row) => shortName(row.test) },
            { key: "m", label: "Score", numeric: true, render: (row) => pct(score(row)) },
            { key: "s", label: "Structure", numeric: true, render: (row) => pct(row.structure) },
            { key: "a", label: "Accuracy", numeric: true, render: (row) => pct(row.accuracy) },
          ]}
          rows={(data.cross_eval.pairs || []).map((pair) => ({
            key: `${pair.train}:${pair.test}`,
            ...pair,
          }))}
        />
      ) : null}
    </section>
  );
}

export default function ExperimentsPage() {
  return (
    <div className="page contrast-page experiments-page">
      <div className="atmosphere" aria-hidden="true" />
      <header className="contrast-hero">
        <p className="eyebrow">Joins · group by · aggregates · filters</p>
        <h1>Transfer</h1>
        <p className="lede">
          QuWARTS vs DocETL on four sets of Player questions, then the same databases asked a
          different set of questions.
        </p>
      </header>
      <main>
        <ComparisonSection />
        <TransferSection />
      </main>
    </div>
  );
}
