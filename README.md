# QuWARTS

Query Workload Aware Relational Table Synthesis from Unstructured Text.

## What's this?

Most enterprise data is stuck in unstructured text (notes, reports, contracts). Running SQL-style queries over that is painful—RAG misses stuff, and per-query extraction is slow/expensive.

QuWARTS pre-extracts structured tables **once**, but uses your historical query workload to decide what to extract and how to normalize it. Result: fast queries + accurate results.

## Repo layout

```
├── frontend/          # Next.js demo UI
│   └── src/           # React components, dashboard, etc.
```

## Quick start (frontend)

```bash
cd frontend
npm install
npm run dev
```

Then hit http://localhost:3000.

## Demo video

https://youtu.be/Q8KdDWwFWX0

