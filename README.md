# Gold Futures Monitor — Stage 1

iPhone-first static PWA prototype using Demo/Test Data.

## Included
- GCZ6 as fixed Stage-1 active/center contract
- Settlement / Volume / Open Interest charts
- 1M / 3M / 6M / 1Y
- Tap chart to inspect Date / Contract / Settlement / Volume / OI / OI Change
- PWA manifest + service worker
- No backend and no CME credentials in frontend

## Deploy
Upload this folder to a static host such as GitHub Pages, Cloudflare Pages, or Vercel.
Open the HTTPS URL in iPhone Safari and use Share → Add to Home Screen.

## Next stage
Replace `data/demo-data.json` with an API endpoint backed by a server-side CME Daily Bulletin PG62 ingestion job. Keep credentials/server access off the client.
