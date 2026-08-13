import data from "./experiments-data.json";

const WORKLOADS = data.workloads || [];

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function tokens(value) {
  if (value == null) return "—";
  return Number(value).toLocaleString("en-US");
}

function mainScore(row) {
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
  return WORKLOADS.find((row) => row.id === workloadId)?.short || workloadId;
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

function ContrastSection() {
  const rows = data.contrast_25pct.rows.map((row) => {
    const qMain = mainScore(row.quwarts);
    const dMain = mainScore(row.docetl);
    return {
      key: row.workload_id,
      ...row,
      qMain,
      dMain,
      dMainDelta: qMain - dMain,
    };
  });
  return (
    <section className="exp-section" id="contrast">
      <h2>QuWARTS vs DocETL at 25% tokens</h2>
      <p>
        Published contrast harvest. QuWARTS used about one quarter of DocETL’s tokens and still
        wins every workload on the main score.
      </p>
      <ScoreTable
        columns={[
          { key: "w", label: "Workload", render: (row) => shortName(row.workload_id) },
          { key: "qa", label: "Q acc", numeric: true, render: (row) => pct(row.quwarts.accuracy) },
          { key: "da", label: "D acc", numeric: true, render: (row) => pct(row.docetl.accuracy) },
          { key: "qs", label: "Q structure", numeric: true, render: (row) => pct(row.quwarts.structure) },
          { key: "ds", label: "D structure", numeric: true, render: (row) => pct(row.docetl.structure) },
          { key: "qm", label: "Q main @20%", numeric: true, render: (row) => pct(row.qMain) },
          { key: "dm", label: "D main @20%", numeric: true, render: (row) => pct(row.dMain) },
          {
            key: "delta",
            label: "Main Δ",
            numeric: true,
            className: (row) => deltaClass(row.dMainDelta),
            render: (row) => signedPct(row.dMainDelta),
          },
          { key: "qt", label: "Q tokens", numeric: true, render: (row) => tokens(row.quwarts.tokens) },
          { key: "dt", label: "D tokens", numeric: true, render: (row) => tokens(row.docetl.tokens) },
        ]}
        rows={rows}
      />
    </section>
  );
}

function LineageSection() {
  const prior = Object.fromEntries(data.prior_quwarts.rows.map((row) => [row.workload_id, row]));
  const current = Object.fromEntries(data.contrast_25pct.rows.map((row) => [row.workload_id, row.quwarts]));
  const rows = WORKLOADS.map((workload) => {
    const before = prior[workload.id];
    const after = current[workload.id];
    const beforeMain = mainScore(before);
    const afterMain = mainScore(after);
    return {
      key: workload.id,
      workload_id: workload.id,
      before,
      after,
      beforeMain,
      afterMain,
      delta: afterMain - beforeMain,
    };
  });
  return (
    <section className="exp-section" id="lineage">
      <h2>QuWARTS before and after taxonomy</h2>
      <p>
        Same ~25% budgets. The earlier contrast lost groupby and filterjoin because closed
        position vocabularies were not mapped. Forced taxonomy reversed that, except join, which
        dropped from a stronger earlier run.
      </p>
      <ScoreTable
        columns={[
          { key: "w", label: "Workload", render: (row) => shortName(row.workload_id) },
          { key: "ba", label: "Before acc", numeric: true, render: (row) => pct(row.before.accuracy) },
          { key: "aa", label: "After acc", numeric: true, render: (row) => pct(row.after.accuracy) },
          { key: "bm", label: "Before main", numeric: true, render: (row) => pct(row.beforeMain) },
          { key: "am", label: "After main", numeric: true, render: (row) => pct(row.afterMain) },
          {
            key: "delta",
            label: "Main Δ",
            numeric: true,
            className: (row) => deltaClass(row.delta),
            render: (row) => signedPct(row.delta),
          },
        ]}
        rows={rows}
      />
    </section>
  );
}

function CrossEvalSection() {
  const ids = WORKLOADS.map((row) => row.id);
  const inWorkload = Object.fromEntries(
    data.contrast_25pct.rows.map((row) => [
      row.workload_id,
      {
        accuracy: row.quwarts.accuracy,
        structure: row.quwarts.structure,
        query_score: row.quwarts.query_score,
        main: mainScore(row.quwarts),
        kind: "in-workload",
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
    <section className="exp-section" id="cross-eval">
      <h2>Cross-workload transfer</h2>
      <p>{data.cross_eval.method}</p>
      <p>{data.cross_eval.status}</p>
      <div className="exp-table-wrap">
        <table className="exp-table exp-matrix">
          <thead>
            <tr>
              <th>Train ↓ / test →</th>
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
                  const score = value.main ?? mainScore(value);
                  const pending = value.kind === "pending";
                  return (
                    <td
                      key={test}
                      className={`num ${train === test ? "matrix-diag" : ""} ${pending ? "matrix-pending" : ""}`}
                    >
                      {pending ? (
                        <span>pending</span>
                      ) : (
                        <>
                          <strong>{pct(score)}</strong>
                          <small>
                            {pct(value.accuracy)} acc · {pct(value.structure)} F2
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
            { key: "tr", label: "Train", render: (row) => shortName(row.train) },
            { key: "te", label: "Test", render: (row) => shortName(row.test) },
            { key: "a", label: "Accuracy", numeric: true, render: (row) => pct(row.accuracy) },
            { key: "s", label: "Structure", numeric: true, render: (row) => pct(row.structure) },
            { key: "m", label: "Main", numeric: true, render: (row) => pct(mainScore(row)) },
            { key: "q", label: "QS @20%", numeric: true, render: (row) => pct(row.query_score) },
            {
              key: "ok",
              label: "Compiled",
              numeric: true,
              render: (row) => (row.compiled_ok_count == null ? "—" : String(row.compiled_ok_count)),
            },
          ]}
          rows={(data.cross_eval.pairs || []).map((pair) => ({
            key: `${pair.train}:${pair.test}`,
            ...pair,
          }))}
        />
      ) : (
        <p className="exp-caveat">
          Off-diagonal cells fill automatically after{" "}
          <code>python3 "case study/harvest_player_experiments.py"</code> sees a
          <code> cross_eval_index.csv</code> on HPC.
        </p>
      )}
    </section>
  );
}

export default function ExperimentsPage() {
  return (
    <div className="page contrast-page experiments-page">
      <div className="atmosphere" aria-hidden="true" />
      <header className="contrast-hero">
        <p className="eyebrow">Four workloads · transfer</p>
        <h1>{data.title}</h1>
        <p className="lede">{data.subtitle}</p>
        <div className="hero-metrics">
          {data.score_definitions.map((item) => (
            <div key={item.id}>
              <span className="metric-label">{item.name}</span>
              <strong>{item.formula}</strong>
            </div>
          ))}
        </div>
      </header>
      <main>
        <section className="exp-section" id="timeline">
          <h2>What we tried</h2>
          <ol className="exp-timeline">
            {data.timeline.map((item) => (
              <li key={item.title}>
                <span>{item.when}</span>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
              </li>
            ))}
          </ol>
        </section>
        <ContrastSection />
        <LineageSection />
        <CrossEvalSection />
        {(data.remaining || []).length > 0 ? (
          <section className="exp-section" id="remaining">
            <h2>Still open</h2>
            <ul>
              {data.remaining.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </main>
      <footer className="footer">
        <p>
          Numbers are taken from harvested evaluations and the HPC logs pasted into this case
          study. Main score is structure F2 × cell F1 at 20% relative error.
        </p>
      </footer>
    </div>
  );
}
