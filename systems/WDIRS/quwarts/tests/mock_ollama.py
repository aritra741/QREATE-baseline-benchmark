"""A stand-in Ollama server for testing the plumbing: answers /api/chat from recorded OpenRouter responses
(looked up by the prompt's hash in the given journals), and with every field null otherwise."""
import hashlib, json, re, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port, journals = int(sys.argv[1]), sys.argv[2:]
recorded = {}
for j in journals:
    for line in open(j):
        if line.strip():
            r = json.loads(line); recorded[r["prompt_sha"]] = r["response"]
hits = {"hit": 0, "miss": 0}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:7b-instruct"}]} if self.path == "/api/tags" else hits)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        text = recorded.get(hashlib.sha256(prompt.encode()).hexdigest())
        hits["hit" if text else "miss"] += 1
        if text is None:
            names = re.findall(r"^- ([A-Za-z0-9_]+) \(", prompt, flags=re.M)
            text = json.dumps({"fields": {n: None for n in names}})
        self._send({"message": {"role": "assistant", "content": text}, "prompt_eval_count": len(prompt) // 4,
                    "eval_count": len(text) // 4, "done": True})

ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
