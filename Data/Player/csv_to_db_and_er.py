#!/usr/bin/env python3
"""
Load all CSV files in Data/Player into a SQLite database, then generate an ER diagram.
Usage: python csv_to_db_and_er.py
"""

import csv
import sqlite3
import os
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "player.db"
ER_MERMAID_PATH = SCRIPT_DIR / "er_diagram.mmd"
ER_HTML_PATH = SCRIPT_DIR / "er_diagram.html"


def strip_headers_and_values(row_dict):
    """Strip leading/trailing whitespace from keys and string values."""
    return {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row_dict.items()}


def load_csv_to_table(cursor, csv_path, table_name):
    """Load a CSV file into a SQLite table. Infers types and creates table."""
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        rows = [strip_headers_and_values(r) for r in reader]
    if not rows:
        return
    columns = list(rows[0].keys())
    # SQLite-friendly column names
    col_safe = [c.replace(" ", "_").replace("-", "_") for c in columns]
    
    # Simple type inference and data cleaning
    col_types = []
    for i, col in enumerate(columns):
        # Sample values to guess type
        sample_vals = [r.get(col) for r in rows[:20] if r.get(col)]
        is_num = True
        has_val = False
        for val in sample_vals:
            has_val = True
            v = val.replace(",", "").strip()
            if not v: continue
            try:
                float(v)
            except ValueError:
                is_num = False
                break
        if has_val and is_num:
            col_types.append("REAL")
        else:
            col_types.append("TEXT")

    col_defs = ", ".join(f'"{c}" {t}' for c, t in zip(col_safe, col_types))
    placeholders = ", ".join("?" for _ in col_safe)
    cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
    
    for row in rows:
        vals = []
        for i, col in enumerate(columns):
            val = row.get(col)
            if val is None or val.strip() == "":
                vals.append(None)
            elif col_types[i] == "REAL":
                try:
                    vals.append(float(val.replace(",", "").strip()))
                except ValueError:
                    vals.append(val)
            else:
                vals.append(val)
        cursor.execute(f'INSERT INTO "{table_name}" ({", ".join(chr(34)+c+chr(34) for c in col_safe)}) VALUES ({placeholders})', vals)


def build_database():
    """Create SQLite DB and load all CSVs."""
    csv_files = [
        ("city", "city.csv"),
        ("owner", "owner.csv"),
        ("team", "team.csv"),
        ("player", "player.csv"),
    ]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for table_name, filename in csv_files:
        path = SCRIPT_DIR / filename
        if path.exists():
            load_csv_to_table(cur, path, table_name)
            print(f"Loaded {path.name} -> table '{table_name}'")
    conn.commit()
    conn.close()
    print(f"Database written to: {DB_PATH}")


def get_table_columns(cursor, table_name):
    """Return list of (name, type) for table."""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [(r[1], r[2]) for r in cursor.fetchall()]


def _mermaid_type(sqlite_type):
    """Map SQLite type to Mermaid attribute type."""
    t = (sqlite_type or "").upper()
    if "INT" in t:
        return "int"
    if "REAL" in t or "FLOAT" in t:
        return "float"
    return "string"


def generate_er_mermaid():
    """Generate Mermaid ER diagram from schema and known relationships."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    lines = ["erDiagram", ""]

    for table in tables:
        cols = get_table_columns(cur, table)
        lines.append(f"    {table} {{")
        for name, typ in cols:
            m_type = _mermaid_type(typ)
            lines.append(f"        {m_type} {name}")
        lines.append("    }")
        lines.append("")

    # Relationships: player.team -> team.team_name, owner.nba_team -> team.team_name, team.location -> city.city_name
    lines.append("    player }o--|| team : team")
    lines.append("    owner }o--|| team : nba_team")
    lines.append("    team }o--|| city : location")
    lines.append("")

    conn.close()

    text = "\n".join(lines)
    ER_MERMAID_PATH.write_text(text, encoding="utf-8")
    print(f"Mermaid ER diagram written to: {ER_MERMAID_PATH}")


def generate_er_html():
    """Generate HTML file that renders the Mermaid ER diagram in the browser."""
    mermaid_code = ER_MERMAID_PATH.read_text(encoding="utf-8")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Player DB – ER Diagram</title>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
    mermaid.init({{ startOnLoad: true, theme: 'neutral' }});
  </script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem; background: #f5f5f5; }}
    h1 {{ color: #333; }}
    .mermaid {{ background: white; padding: 1rem; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>Player database – ER diagram</h1>
  <p>Tables: city, owner, team, player. Relationships: player→team, owner→team, team→city.</p>
  <pre class="mermaid">
{mermaid_code}
  </pre>
</body>
</html>
"""
    ER_HTML_PATH.write_text(html, encoding="utf-8")
    print(f"HTML ER diagram written to: {ER_HTML_PATH} (open in browser to view)")


def main():
    os.chdir(SCRIPT_DIR)
    build_database()
    generate_er_mermaid()
    generate_er_html()
    print("Done. Open er_diagram.html in a browser to view the ER diagram.")


if __name__ == "__main__":
    main()
