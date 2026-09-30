"""A stand-in Ollama server whose answer for a (document, field) never depends on the prompt: it returns the
value a fixed earlier read stored for that document and field (``robust_raw.db`` of the replay), whatever the
other fields, the usage phrases or the chunking. Run the drift experiment against it and every level's
extraction is identical by construction, so any difference between levels comes from the pipeline itself.

    python quwarts/tests/oracle_ollama.py PORT CORPUS [CORPUS...]   (PYTHONPATH and QUWARTS_DRIFT_DESIGN set)
"""
import json, re, sqlite3, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from quwarts.core.adapt import controller as C
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R

port, corpora = int(sys.argv[1]), sys.argv[2:]
lines: dict[str, set] = {}      # a line of text -> {(corpus, table, doc)}
values: dict[tuple, dict] = {}  # (corpus, table, doc) -> {column (lower case): value}
columns: dict[tuple, set] = {}  # (corpus, table) -> columns
for c in corpora:
    ctx = R.context(c)
    conn = sqlite3.connect(R.fixed_db(c, "robust_raw"))
    for t, docs in ctx.docs.items():
        try:
            cur = conn.execute(f'SELECT * FROM "{t}"')
        except sqlite3.OperationalError:
            continue
        names = [d[0].lower() for d in cur.description]
        columns[(c, t)] = set(names)
        for row in cur.fetchall():
            r = dict(zip(names, row))
            values[(c, t, C._doc_name(r["doc_id"]))] = r
        for d, path in docs.items():
            for line in read_document(path).splitlines():
                line = line.strip()
                if len(line) >= 40:
                    lines.setdefault(line, set()).add((c, t, d))
stats = {"calls": 0, "unmatched": 0, "ambiguous": 0}


def answer(prompt: str) -> str:
    stats["calls"] += 1
    part = re.search(r"PART (\d+) OF (\d+):\n", prompt)
    body = prompt.split("FIELDS:")[0]
    fields = re.findall(r"^- ([A-Za-z0-9_]+) \(", prompt.split("FIELDS:")[-1], flags=re.M)
    cands = None
    for line in body.splitlines():
        hit = lines.get(line.strip())
        if hit:
            cands = hit if cands is None else (cands & hit) or cands
            if len(cands) == 1:
                break
    out = {f: None for f in fields}
    if not cands:
        stats["unmatched"] += 1
    else:
        # the table whose columns contain the asked fields
        cands = sorted(cands, key=lambda k: -len({f.lower() for f in fields} & columns.get(k[:2], set())))
        if len(cands) > 1:
            stats["ambiguous"] += 1
        row = values.get(cands[0], {})
        if part is None or part.group(1) == "1":  # a chunked document states everything in its first part
            out = {f: row.get(f.lower()) for f in fields}
    payload = {"fields": out}
    if part is not None:
        payload["context_for_next_part"] = "same document"
    return json.dumps(payload)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:7b-instruct"}]} if self.path == "/api/tags" else stats)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        text = answer(prompt)
        self._send({"message": {"role": "assistant", "content": text}, "prompt_eval_count": len(prompt) // 4,
                    "eval_count": len(text) // 4, "done": True})


print("oracle ready", len(values), "rows", flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
