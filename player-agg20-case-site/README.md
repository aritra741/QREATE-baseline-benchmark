# QuWARTS case study site

Static site that compares QuWARTS and DocETL on 20 Player questions.

## Comments

Select any text to add a Google Docs-style comment. The first time you comment,
the site asks for your name and remembers it in this browser. Comments are stored
on a shared backend so other people can see them.

Local development uses a shared JSON file at `data/comments.json`.
Production on Vercel uses Vercel KV / Upstash Redis.

## Local

```bash
cd player-agg20-case-site
npm install
npm run dev
```

`npm run dev` starts the Vite app and a local comments API on port 8787.
Open two browser windows against the same local URL to confirm comments sync.

## Deploy on Vercel

```bash
cd player-agg20-case-site
npx vercel
```

Or set the Vercel project root to `player-agg20-case-site`.

- Build command: `npm run build`
- Output folder: `dist`

### Enable shared comments on Vercel

1. Open the Vercel project → **Storage** → create a **KV** store (Upstash Redis).
2. Connect the store to the project. Vercel injects:
   - `KV_REST_API_URL`
   - `KV_REST_API_TOKEN`
3. Redeploy.

Until KV is connected, the site still works, but comments stay local to each browser.
