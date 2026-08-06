import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addReply,
  authorHue,
  authorInitials,
  createThread,
  deleteThread,
  formatRelativeTime,
  getAuthorName,
  loadThreads,
  resolveThread,
  saveThreads,
  setAuthorName,
} from "./commentsStore";

function selectionContext() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  const root = document.querySelector(".page-content");
  if (!root || !root.contains(range.commonAncestorContainer)) return null;

  const quote = selection.toString().replace(/\s+/g, " ").trim();
  if (quote.length < 2) return null;

  const before = document.createRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const prefix = before.toString().slice(-40);

  const after = document.createRange();
  after.selectNodeContents(root);
  after.setStart(range.endContainer, range.endOffset);
  const suffix = after.toString().slice(0, 40);

  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) return null;

  return {
    quote,
    prefix,
    suffix,
    rect: {
      top: rect.top + window.scrollY,
      left: rect.left + window.scrollX,
      width: rect.width,
      height: rect.height,
    },
  };
}

function clearSelection() {
  const selection = window.getSelection();
  if (selection) selection.removeAllRanges();
}

function NameModal({ open, onSubmit, onCancel }) {
  const [name, setName] = useState("");
  if (!open) return null;
  return (
    <div className="comment-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="name-modal-title">
      <form
        className="comment-modal"
        onSubmit={(event) => {
          event.preventDefault();
          const cleaned = name.trim();
          if (!cleaned) return;
          onSubmit(cleaned);
        }}
      >
        <h3 id="name-modal-title">What is your name?</h3>
        <p>I will use this name on your comments. You will not be asked again on this browser.</p>
        <input
          autoFocus
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Your name"
          maxLength={60}
        />
        <div className="comment-modal-actions">
          <button type="button" className="comment-btn ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="comment-btn primary" disabled={!name.trim()}>
            Continue
          </button>
        </div>
      </form>
    </div>
  );
}

function Composer({ placeholder, onSubmit, onCancel, autoFocus = true }) {
  const [body, setBody] = useState("");
  return (
    <form
      className="comment-composer"
      onSubmit={(event) => {
        event.preventDefault();
        const cleaned = body.trim();
        if (!cleaned) return;
        onSubmit(cleaned);
        setBody("");
      }}
    >
      <textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={placeholder}
        rows={3}
        autoFocus={autoFocus}
      />
      <div className="comment-composer-actions">
        {onCancel ? (
          <button type="button" className="comment-btn ghost" onClick={onCancel}>
            Cancel
          </button>
        ) : null}
        <button type="submit" className="comment-btn primary" disabled={!body.trim()}>
          Comment
        </button>
      </div>
    </form>
  );
}

function Avatar({ name }) {
  const hue = authorHue(name);
  return (
    <span
      className="comment-avatar"
      style={{ background: `hsl(${hue} 45% 42%)` }}
      aria-hidden="true"
    >
      {authorInitials(name)}
    </span>
  );
}

function CommentBubble({ comment }) {
  return (
    <div className="comment-bubble">
      <Avatar name={comment.author} />
      <div className="comment-bubble-body">
        <div className="comment-meta">
          <strong>{comment.author}</strong>
          <span>{formatRelativeTime(comment.createdAt)}</span>
        </div>
        <p>{comment.body}</p>
      </div>
    </div>
  );
}

function ThreadCard({
  thread,
  active,
  onSelect,
  onReply,
  onResolve,
  onDelete,
  ensureAuthor,
}) {
  const [replying, setReplying] = useState(false);
  return (
    <article
      className={`comment-thread ${active ? "active" : ""} ${thread.resolved ? "resolved" : ""}`}
      onClick={onSelect}
    >
      {thread.quote ? (
        <button type="button" className="comment-quote" onClick={onSelect}>
          {thread.quote}
        </button>
      ) : null}
      {thread.comments.map((comment) => (
        <CommentBubble key={comment.id} comment={comment} />
      ))}
      {replying ? (
        <Composer
          placeholder="Reply"
          onCancel={() => setReplying(false)}
          onSubmit={async (body) => {
            const author = await ensureAuthor();
            if (!author) return;
            onReply(body, author);
            setReplying(false);
          }}
        />
      ) : (
        <div className="comment-thread-actions">
          <button
            type="button"
            className="comment-btn ghost"
            onClick={(event) => {
              event.stopPropagation();
              setReplying(true);
            }}
          >
            Reply
          </button>
          <button
            type="button"
            className="comment-btn ghost"
            onClick={(event) => {
              event.stopPropagation();
              onResolve(!thread.resolved);
            }}
          >
            {thread.resolved ? "Reopen" : "Resolve"}
          </button>
          <button
            type="button"
            className="comment-btn ghost danger"
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
          >
            Delete
          </button>
        </div>
      )}
    </article>
  );
}

export default function CommentsSystem({ children }) {
  const [threads, setThreads] = useState(() => loadThreads());
  const [author, setAuthor] = useState(() => getAuthorName());
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [namePrompt, setNamePrompt] = useState(null);
  const nameResolver = useRef(null);

  useEffect(() => {
    saveThreads(threads);
  }, [threads]);

  useEffect(() => {
    document.body.classList.toggle("comments-open", panelOpen);
    return () => document.body.classList.remove("comments-open");
  }, [panelOpen]);

  const ensureAuthor = useCallback(() => {
    const existing = getAuthorName() || author;
    if (existing) {
      setAuthor(existing);
      return Promise.resolve(existing);
    }
    return new Promise((resolve) => {
      nameResolver.current = resolve;
      setNamePrompt({ mode: "ask" });
    });
  }, [author]);

  const openComposerForSelection = useCallback(() => {
    const context = selectionContext();
    if (!context) return;
    setDraft(context);
    setPanelOpen(true);
    clearSelection();
  }, []);

  useEffect(() => {
    const onMouseUp = (event) => {
      if (event.target.closest?.(".comment-ui")) return;
      window.setTimeout(() => {
        const context = selectionContext();
        if (!context) {
          setDraft((current) => (current?.mode === "floating" ? null : current));
          return;
        }
        setDraft({ ...context, mode: "floating" });
      }, 10);
    };
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        openComposerForSelection();
      }
    };
    document.addEventListener("mouseup", onMouseUp);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openComposerForSelection]);

  useEffect(() => {
    const marks = document.querySelectorAll("mark.comment-mark");
    marks.forEach((mark) => {
      const text = document.createTextNode(mark.textContent || "");
      mark.replaceWith(text);
    });

    const root = document.querySelector(".page-content");
    if (!root) return;

    for (const thread of threads) {
      if (!thread.quote || thread.resolved) continue;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const value = node.nodeValue || "";
        const index = value.indexOf(thread.quote);
        if (index >= 0 && !node.parentElement?.closest("mark.comment-mark, .comment-ui, button, a, textarea, input")) {
          const range = document.createRange();
          range.setStart(node, index);
          range.setEnd(node, index + thread.quote.length);
          const mark = document.createElement("mark");
          mark.className = `comment-mark ${activeId === thread.id ? "active" : ""}`;
          mark.dataset.threadId = thread.id;
          mark.title = "Open comment";
          mark.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            setActiveId(thread.id);
            setPanelOpen(true);
          });
          try {
            range.surroundContents(mark);
          } catch {
            /* skip awkward split nodes */
          }
          break;
        }
        node = walker.nextNode();
      }
    }
  }, [threads, activeId, panelOpen]);

  const openCount = useMemo(
    () => threads.filter((thread) => !thread.resolved).length,
    [threads]
  );

  const sortedThreads = useMemo(
    () =>
      [...threads].sort((a, b) => {
        if (a.resolved !== b.resolved) return a.resolved ? 1 : -1;
        return String(b.createdAt).localeCompare(String(a.createdAt));
      }),
    [threads]
  );

  return (
    <div className={`comments-shell ${panelOpen ? "with-panel" : ""}`}>
      <div className="page-content">{children}</div>

      {draft?.mode === "floating" ? (
        <div
          className="comment-ui comment-floating"
          style={{
            top: draft.rect.top - 44,
            left: Math.min(
              draft.rect.left + draft.rect.width / 2,
              window.scrollX + window.innerWidth - 120
            ),
          }}
        >
          <button
            type="button"
            className="comment-fab"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setDraft({ ...draft, mode: "compose" });
              setPanelOpen(true);
            }}
          >
            Add comment
          </button>
        </div>
      ) : null}

      <button
        type="button"
        className={`comment-ui comment-panel-toggle ${panelOpen ? "open" : ""}`}
        onClick={() => setPanelOpen((value) => !value)}
        aria-expanded={panelOpen}
      >
        Comments{openCount ? ` (${openCount})` : ""}
      </button>

      <aside className={`comment-ui comment-panel ${panelOpen ? "open" : ""}`} aria-label="Comments">
        <header className="comment-panel-header">
          <div>
            <h2>Comments</h2>
            <p>Select any text, then add a comment. Replies stay in the same thread.</p>
          </div>
          <button type="button" className="comment-btn ghost" onClick={() => setPanelOpen(false)}>
            Close
          </button>
        </header>

        {author ? (
          <div className="comment-signed-in">
            <Avatar name={author} />
            <span>Commenting as <strong>{author}</strong></span>
            <button
              type="button"
              className="comment-btn ghost"
              onClick={() => {
                setNamePrompt({ mode: "change" });
              }}
            >
              Change
            </button>
          </div>
        ) : (
          <div className="comment-signed-in">
            <span>You have not set a name yet.</span>
            <button type="button" className="comment-btn ghost" onClick={() => setNamePrompt({ mode: "ask" })}>
              Set name
            </button>
          </div>
        )}

        {draft?.mode === "compose" ? (
          <div className="comment-new">
            <div className="comment-quote-preview">{draft.quote}</div>
            <Composer
              placeholder="Add a comment"
              onCancel={() => setDraft(null)}
              onSubmit={async (body) => {
                const nextAuthor = await ensureAuthor();
                if (!nextAuthor) return;
                const thread = createThread({
                  quote: draft.quote,
                  prefix: draft.prefix,
                  suffix: draft.suffix,
                  author: nextAuthor,
                  body,
                });
                setThreads((current) => [thread, ...current]);
                setActiveId(thread.id);
                setDraft(null);
              }}
            />
          </div>
        ) : null}

        <div className="comment-thread-list">
          {sortedThreads.length ? (
            sortedThreads.map((thread) => (
              <ThreadCard
                key={thread.id}
                thread={thread}
                active={activeId === thread.id}
                ensureAuthor={ensureAuthor}
                onSelect={() => setActiveId(thread.id)}
                onReply={(body, replyAuthor) => {
                  setThreads((current) => addReply(current, thread.id, { author: replyAuthor, body }));
                }}
                onResolve={(resolved) => {
                  setThreads((current) => resolveThread(current, thread.id, resolved));
                }}
                onDelete={() => {
                  setThreads((current) => deleteThread(current, thread.id));
                  if (activeId === thread.id) setActiveId(null);
                }}
              />
            ))
          ) : (
            <p className="comment-empty">
              No comments yet. Select text on the page and click Add comment.
            </p>
          )}
        </div>
      </aside>

      <NameModal
        open={Boolean(namePrompt)}
        onCancel={() => {
          if (nameResolver.current) {
            nameResolver.current("");
            nameResolver.current = null;
          }
          setNamePrompt(null);
        }}
        onSubmit={(name) => {
          const saved = setAuthorName(name);
          setAuthor(saved);
          setNamePrompt(null);
          if (nameResolver.current) {
            nameResolver.current(saved);
            nameResolver.current = null;
          }
        }}
      />
    </div>
  );
}
