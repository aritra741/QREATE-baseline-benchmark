-- ============================================================
-- UQE Single-Table Trend Queries (Player Dataset)
-- 10 queries: SELECT, FILTER, AGGREGATION over the player table.
-- Q1 (simple select) → Q10 (complex aggregation with semantic filter)
-- All queries are single-table over 'player' — within UQE's design scope.
-- ============================================================

-- ── TIER 1: Simple SELECT + extraction (no filter) ──────────────────────────

-- Q1: Extract basic attributes for all players
SELECT name, nationality, age, team FROM player

-- Q2: Extract a wider set of attributes for all players
SELECT name, position, college, draft_pick FROM player

-- ── TIER 2: SELECT with structured WHERE filter ─────────────────────────────

-- Q3: Players older than 30
SELECT name, nationality, age, team FROM player WHERE age > 30

-- Q4: Players with a known draft pick (drafted players)
SELECT name, college, draft_pick, team FROM player WHERE draft_pick > 0

-- ── TIER 3: SELECT with semantic WHERE filter ───────────────────────────────

-- Q5: Players from USA (structured categorical filter)
SELECT name, nationality, team FROM player WHERE nationality = 'American'

-- Q6: Players in backcourt role (structured categorical filter)
SELECT name, position, team FROM player WHERE position = 'Backcourt'

-- ── TIER 4: COUNT aggregation with structured filter ────────────────────────

-- Q7: Count of players older than 25
SELECT COUNT(*) FROM player WHERE age > 25

-- Q8: Count of players with MVP awards
SELECT COUNT(*) FROM player WHERE mvp_awards > 0

-- ── TIER 5: GROUP BY aggregation (virtual column taxonomy) ──────────────────

-- Q9: Count players grouped by position
SELECT position, COUNT(*) FROM player GROUP BY position

-- Q10: Count players grouped by nationality
SELECT nationality, COUNT(*) FROM player GROUP BY nationality
