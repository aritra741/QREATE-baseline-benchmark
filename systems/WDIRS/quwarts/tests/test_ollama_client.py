import socket
import subprocess
import sys
import time
from pathlib import Path


def test_ollama_caller_against_mock(tmp_path):
    from quwarts.core.llm import ollama

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    empty = tmp_path / "journal.jsonl"
    empty.write_text("")
    mock = Path(__file__).with_name("mock_ollama.py")
    proc = subprocess.Popen([sys.executable, str(mock), str(port), str(empty)])
    try:
        host = f"127.0.0.1:{port}"
        for _ in range(50):
            try:
                assert "qwen2.5:7b-instruct" in ollama.ping(host)
                break
            except Exception:
                time.sleep(0.1)
        seen = []
        caller = ollama.make_caller(host=host, on_usage=lambda p, u: seen.append(u))
        text = caller.complete("FIELDS:\n- field (text): x\n- nationality (text): y\n", "test")
        assert '"field": null' in text and caller.ledger.spent > 0
        assert seen and seen[0]["input"] > 0 and seen[0]["num_ctx"] == 16384 and not seen[0]["maybe_truncated"]
    finally:
        proc.kill()
