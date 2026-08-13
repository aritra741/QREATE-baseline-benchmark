const AUTHOR_KEY = "quwarts-case-author";
const THREADS_KEY = "quwarts-case-threads-v1";
const COMMENTS_API = "/api/comments";

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

function parseThreadList(raw) {
  if (!raw) return [];
  const parsed = JSON.parse(raw);
  if (Array.isArray(parsed)) return parsed;
  if (Array.isArray(parsed?.threads)) return parsed.threads;
  return [];
}

export function loadLocalThreads() {
  try {
    const collected = [];
    const keys = new Set([THREADS_KEY]);
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && key.startsWith("quwarts-case-threads")) keys.add(key);
    }
    for (const key of keys) {
      collected.push(...parseThreadList(localStorage.getItem(key)));
    }
    return mergeThreads(collected, []);
  } catch {
    return [];
  }
}

export function localHasUnsynced(localThreads, remoteThreads) {
  const remoteThreadIds = new Set((remoteThreads || []).map((thread) => thread?.id).filter(Boolean));
  const remoteCommentIds = new Set(
    (remoteThreads || []).flatMap((thread) =>
      (thread?.comments || []).map((comment) => comment?.id).filter(Boolean)
    )
  );
  for (const thread of localThreads || []) {
    if (!thread?.id) continue;
    if (!remoteThreadIds.has(thread.id)) return true;
    const remote = (remoteThreads || []).find((item) => item.id === thread.id);
    if (remote && Boolean(remote.resolved) !== Boolean(thread.resolved)) return true;
    for (const comment of thread.comments || []) {
      if (comment?.id && !remoteCommentIds.has(comment.id)) return true;
    }
  }
  return false;
}

export function saveLocalThreads(threads) {
  try {
    localStorage.setItem(THREADS_KEY, JSON.stringify(threads));
  } catch {
    /* ignore quota */
  }
}

function commentStamp(comment) {
  return String(comment?.createdAt || "");
}

function threadStamp(thread) {
  const comments = Array.isArray(thread?.comments) ? thread.comments : [];
  const latest = comments.reduce((max, comment) => {
    const value = commentStamp(comment);
    return value > max ? value : max;
  }, String(thread?.createdAt || ""));
  return latest;
}

export function mergeThreads(localThreads, remoteThreads) {
  const byId = new Map();
  for (const thread of [...(remoteThreads || []), ...(localThreads || [])]) {
    if (!thread || !thread.id) continue;
    const existing = byId.get(thread.id);
    if (!existing) {
      byId.set(thread.id, {
        ...thread,
        comments: Array.isArray(thread.comments) ? [...thread.comments] : [],
      });
      continue;
    }
    const commentsById = new Map();
    for (const comment of [...existing.comments, ...(thread.comments || [])]) {
      if (!comment?.id) continue;
      const prev = commentsById.get(comment.id);
      if (!prev || commentStamp(comment) >= commentStamp(prev)) {
        commentsById.set(comment.id, comment);
      }
    }
    const comments = [...commentsById.values()].sort((a, b) =>
      commentStamp(a).localeCompare(commentStamp(b))
    );
    const preferRemote = threadStamp(thread) >= threadStamp(existing);
    byId.set(thread.id, {
      ...(preferRemote ? thread : existing),
      comments,
      resolved: preferRemote ? Boolean(thread.resolved) : Boolean(existing.resolved),
    });
  }
  return [...byId.values()].sort((a, b) => threadStamp(b).localeCompare(threadStamp(a)));
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

export async function fetchSharedThreads() {
  const response = await fetch(COMMENTS_API, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to load comments (${response.status})`);
  }
  const payload = await response.json();
  return {
    threads: Array.isArray(payload.threads) ? payload.threads : [],
    updatedAt: payload.updatedAt || null,
    shared: Boolean(payload.shared),
  };
}

export async function pushSharedThreads(threads) {
  const response = await fetch(COMMENTS_API, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ threads }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Failed to save comments (${response.status})`);
  }
  const payload = await response.json();
  return {
    threads: Array.isArray(payload.threads) ? payload.threads : threads,
    updatedAt: payload.updatedAt || null,
    shared: Boolean(payload.shared),
  };
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
