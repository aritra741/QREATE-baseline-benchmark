import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DATA_DIR = path.join(ROOT, "data");
const DATA_FILE = path.join(DATA_DIR, "comments.json");
const PORT = Number(process.env.COMMENTS_PORT || 8787);

async function readStore() {
  try {
    const raw = await readFile(DATA_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return {
      threads: Array.isArray(parsed.threads) ? parsed.threads : [],
      updatedAt: parsed.updatedAt || null,
    };
  } catch {
    return { threads: [], updatedAt: null };
  }
}

async function writeStore(threads) {
  await mkdir(DATA_DIR, { recursive: true });
  const payload = {
    threads,
    updatedAt: new Date().toISOString(),
    shared: true,
  };
  await writeFile(DATA_FILE, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return payload;
}

function send(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,PUT,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept",
  });
  res.end(text);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

const server = createServer(async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      send(res, 204, {});
      return;
    }
    const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);
    if (url.pathname !== "/api/comments" && url.pathname !== "/comments") {
      send(res, 404, { error: "Not found" });
      return;
    }
    if (req.method === "GET") {
      const store = await readStore();
      send(res, 200, { ...store, shared: true });
      return;
    }
    if (req.method === "PUT" || req.method === "POST") {
      const body = await readBody(req);
      const threads = Array.isArray(body.threads) ? body.threads : [];
      const store = await writeStore(threads);
      send(res, 200, store);
      return;
    }
    send(res, 405, { error: "Method not allowed" });
  } catch (error) {
    send(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Comments API listening on http://127.0.0.1:${PORT}`);
});
