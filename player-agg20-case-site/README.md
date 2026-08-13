# QuWARTS case study site

Static site that compares QuWARTS and DocETL on 20 Player questions.

The original 20-question case study is at `/`. The four sets of questions are at
`/contrasts`. Transfer scores are at `/experiments`.

## Harvest contrast results

DocETL contrast results are split across timestamped run folders. Stage them
first (includes `evaluation.json` + `query_tables/`), then harvest:

```bash
cd /path/to/UDA-Bench-main

python3 "case study/stage_docetl_contrast_results.py"

python3 "case study/harvest_player_contrast_results.py" \
  --quwarts-root "case study/workloads/runs/quwarts_forced_taxonomy_25pct_20260810" \
  --groupby-root "case study/workloads/runs/quwarts_forced_taxonomy_25pct_20260809" \
  --docetl-root "case study/workloads/runs/docetl_contrast_staged" \
  --output "player-agg20-case-site/src/contrast-data.json"
```

If you skip staging, omit `--docetl-root` and the harvester will look up the
known DocETL paths under `case study/workloads/runs/*/docetl/results/`.

This is the publishing path: it requires both systems' `evaluation.json` for all
four workloads, exactly 20 matching records per evaluation, finite metrics, and
unique manifest IDs. It also attaches ground-truth tables plus system outputs so
`/contrasts` can show missing groups, extra groups, and wrong values. Keep
QuWARTS `serving_bundle/` and DocETL `query_tables/` next to each
`evaluation.json` (do not stage scores alone). Validation happens before the
output is atomically replaced.

If a local bundle already has scores but not tables:

```bash
python3 "case study/contrast_table_enrichment.py" \
  --bundle "player-agg20-case-site/src/contrast-data.json"
```

For a local UI build without detailed HPC artifacts:

```bash
python3 "case study/harvest_player_contrast_results.py" \
  --allow-summary-fallback \
  --output "player-agg20-case-site/src/contrast-data.json"
```

Fallback mode includes all 80 manifest queries but labels per-query system
metrics as unavailable.

## Cross-workload transfer on HPC

The `/experiments` matrix stays `pending` until scores are harvested into
`player-agg20-case-site/src/experiments-data.json`. Raw run folders under
`case study/workloads/runs/` are gitignored, so finishing the eval on HPC is
not enough by itself.

From the repo root, with the WDIRS venv active:

```bash
git pull

python3 "case study/run_and_harvest_player_cross_eval.py" --check
python3 "case study/run_and_harvest_player_cross_eval.py" --run
```

If the 12 pairs already finished and you only need the website files:

```bash
python3 "case study/run_and_harvest_player_cross_eval.py" --harvest-only
```

Then commit the two tracked files the script prints:

```bash
git add player-agg20-case-site/src/experiments-data.json \
        player-agg20-case-site/src/cross_eval_index.csv
git commit -m "Harvest Player cross-workload transfer scores"
git push
```

On the laptop, `git pull` and reload `/experiments`.

`--check` verifies the four sealed 25% taxonomy `serving_bundle` databases.
`--run` reuses those DBs (no re-extraction), scores all 12 train→test pairs,
and harvests the site JSON.

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

Build and preview the exact deployable site:

```bash
cd player-agg20-case-site
npm ci
npm run build
npm run preview -- --host 0.0.0.0
```

## Deploy on Vercel

```bash
cd player-agg20-case-site
npm run build
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
The next time someone with older browser-only comments opens the site, those comments
are copied into shared storage so everyone can see them.
