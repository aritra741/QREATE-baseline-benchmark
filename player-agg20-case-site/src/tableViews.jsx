export function fmtCell(value) {
  if (value == null || value === "") return "∅";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    return Number.isInteger(value) ? String(value) : value.toPrecision(6).replace(/\.?0+$/, "");
  }
  const text = String(value);
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}

export function columnsFromRows(rows, schema) {
  if (schema?.key_columns?.length || schema?.measure_columns?.length) {
    return [...(schema.key_columns || []), ...(schema.measure_columns || [])];
  }
  if (!rows?.length) return [];
  return Object.keys(rows[0]);
}

export function ResultTable({ rows, schema, emptyLabel }) {
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

export function DiffBlock({ title, rows, schema }) {
  return (
    <div className="diff-block">
      <h5>{title}</h5>
      <ResultTable rows={rows} schema={schema} emptyLabel="None." />
    </div>
  );
}

export function WrongValues({ wrong }) {
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
