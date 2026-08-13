const JOIN_RE = /\bJOIN\b/gi;
const AGG_RE = /\b(?:AVG|COUNT|SUM|MIN|MAX)\s*\(/gi;
const GROUP_RE = /\bGROUP BY\s+(.+?)(?:\bHAVING\b|$)/i;

export function sqlProperties(sql) {
  const text = String(sql || "");
  const groupMatch = text.match(GROUP_RE);
  return {
    joins: (text.match(JOIN_RE) || []).length,
    aggregates: (text.match(AGG_RE) || []).length,
    groupKeys: groupMatch
      ? groupMatch[1].split(",").map((part) => part.trim()).filter(Boolean).length
      : 0,
    hasHaving: /\bHAVING\b/i.test(text),
  };
}

function joinLabel(count) {
  if (count <= 0) return "No join";
  if (count === 1) return "1 join";
  return `${count} joins`;
}

function groupLabel(count) {
  if (count <= 1) return "1 grouping column";
  return `${count} grouping columns`;
}

function aggLabel(count) {
  if (count <= 1) return "1 aggregate";
  return `${count} aggregates`;
}

export function variantLabel(workloadId, sql) {
  const props = sqlProperties(sql);
  if (workloadId === "player_groupby20") return groupLabel(props.groupKeys);
  if (workloadId === "player_multiagg20") return aggLabel(props.aggregates);
  return joinLabel(props.joins);
}

function bucket(title, specs, queries) {
  const rows = specs
    .map((spec) => ({
      label: spec.label,
      queries: queries.filter((query) => spec.test(query.props)),
    }))
    .filter((row) => row.queries.length > 0);
  return rows.length ? { title, rows } : null;
}

export function variantTables(workloadId, queries) {
  const tagged = queries.map((query) => ({
    ...query,
    props: sqlProperties(query.sql),
  }));
  const tables = [
    bucket(
      "By number of joins",
      [
        { label: "No join", test: (p) => p.joins === 0 },
        { label: "1 join", test: (p) => p.joins === 1 },
        { label: "2 joins", test: (p) => p.joins === 2 },
        { label: "3 joins", test: (p) => p.joins === 3 },
        { label: "4 or more joins", test: (p) => p.joins >= 4 },
      ],
      tagged
    ),
  ];
  if (workloadId === "player_groupby20") {
    tables.push(
      bucket(
        "By grouping columns",
        [
          { label: "1 grouping column", test: (p) => p.groupKeys <= 1 },
          { label: "2 grouping columns", test: (p) => p.groupKeys === 2 },
          { label: "3 or more grouping columns", test: (p) => p.groupKeys >= 3 },
        ],
        tagged
      )
    );
  }
  if (workloadId === "player_multiagg20") {
    tables.push(
      bucket(
        "By number of aggregates",
        [
          { label: "1 or 2 aggregates", test: (p) => p.aggregates <= 2 },
          { label: "3 aggregates", test: (p) => p.aggregates === 3 },
          { label: "4 or more aggregates", test: (p) => p.aggregates >= 4 },
        ],
        tagged
      ),
      bucket(
        "By HAVING",
        [
          { label: "Has HAVING", test: (p) => p.hasHaving },
          { label: "No HAVING", test: (p) => !p.hasHaving },
        ],
        tagged
      )
    );
  }
  return tables.filter(Boolean);
}
