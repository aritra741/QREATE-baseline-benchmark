const AUTHOR_KEY = "quwarts-case-author";
const THREADS_KEY = "quwarts-case-threads-v1";

function uid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getAuthorName() {
  try {
    return localStorage.getItem(AUTHOR_KEY) || "";
  } catch {
    return "";
  }
}

export function setAuthorName(name) {
  const cleaned = String(name || "").trim();
  if (!cleaned) return "";
  try {
    localStorage.setItem(AUTHOR_KEY, cleaned);
  } catch {
    /* ignore quota */
  }
  return cleaned;
}

export function loadThreads() {
  try {
    const raw = localStorage.getItem(THREADS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveThreads(threads) {
  try {
    localStorage.setItem(THREADS_KEY, JSON.stringify(threads));
  } catch {
    /* ignore quota */
  }
}

export function createThread({ quote, prefix, suffix, author, body }) {
  const now = new Date().toISOString();
  const commentId = uid();
  return {
    id: uid(),
    quote: String(quote || "").slice(0, 500),
    prefix: String(prefix || "").slice(0, 40),
    suffix: String(suffix || "").slice(0, 40),
    createdAt: now,
    resolved: false,
    comments: [
      {
        id: commentId,
        author,
        body: String(body || "").trim(),
        createdAt: now,
      },
    ],
  };
}

export function addReply(threads, threadId, { author, body }) {
  const now = new Date().toISOString();
  return threads.map((thread) => {
    if (thread.id !== threadId) return thread;
    return {
      ...thread,
      comments: [
        ...thread.comments,
        {
          id: uid(),
          author,
          body: String(body || "").trim(),
          createdAt: now,
        },
      ],
    };
  });
}

export function resolveThread(threads, threadId, resolved = true) {
  return threads.map((thread) =>
    thread.id === threadId ? { ...thread, resolved: Boolean(resolved) } : thread
  );
}

export function deleteThread(threads, threadId) {
  return threads.filter((thread) => thread.id !== threadId);
}

export function formatRelativeTime(iso) {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min ago`;
  if (seconds < 86400) return `${Math.max(1, Math.round(seconds / 3600))} hr ago`;
  if (seconds < 604800) return `${Math.max(1, Math.round(seconds / 86400))} days ago`;
  return new Date(iso).toLocaleDateString();
}

export function authorInitials(name) {
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function authorHue(name) {
  let hash = 0;
  for (const ch of String(name || "")) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 360;
}
