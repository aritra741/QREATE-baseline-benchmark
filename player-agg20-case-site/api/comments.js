const KEY = "quwarts-case-comments-v1";

function kvConfig() {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  return { url: url.replace(/\/$/, ""), token };
}

async function kvGet(config) {
  const response = await fetch(`${config.url}/get/${encodeURIComponent(KEY)}`, {
    headers: { Authorization: `Bearer ${config.token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`KV get failed (${response.status})`);
  }
  const payload = await response.json();
  if (!payload.result) {
    return { threads: [], updatedAt: null };
  }
  const parsed = typeof payload.result === "string" ? JSON.parse(payload.result) : payload.result;
  return {
    threads: Array.isArray(parsed.threads) ? parsed.threads : [],
    updatedAt: parsed.updatedAt || null,
  };
}

async function kvSet(config, threads) {
  const body = {
    threads,
    updatedAt: new Date().toISOString(),
    shared: true,
  };
  const encoded = encodeURIComponent(JSON.stringify(body));
  const response = await fetch(`${config.url}/set/${encodeURIComponent(KEY)}/${encoded}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!response.ok) {
    throw new Error(`KV set failed (${response.status})`);
  }
  return body;
}

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

export default async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.end();
    return;
  }

  const config = kvConfig();
  if (!config) {
    send(res, 503, {
      error:
        "Shared comments are not configured. In the Vercel project, create a KV store and reconnect the deployment.",
      shared: false,
      threads: [],
    });
    return;
  }

  try {
    if (req.method === "GET") {
      const store = await kvGet(config);
      send(res, 200, { ...store, shared: true });
      return;
    }

    if (req.method === "PUT" || req.method === "POST") {
      const body = await readBody(req);
      const threads = Array.isArray(body.threads) ? body.threads : [];
      if (threads.length > 500) {
        send(res, 400, { error: "Too many comment threads." });
        return;
      }
      const store = await kvSet(config, threads);
      send(res, 200, store);
      return;
    }

    send(res, 405, { error: "Method not allowed" });
  } catch (error) {
    send(res, 500, {
      error: error instanceof Error ? error.message : String(error),
      shared: false,
    });
  }
}
