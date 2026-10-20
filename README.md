# Player Outfit Banner API — Vercel deploy

**Powered by JIHAD** — Official channel: https://t.me/jihad_x_leaker

## What's in this zip
- `app.py` — Flask app (entrypoint Vercel looks for)
- `requirements.txt` — Flask, requests, Pillow
- `banner_template.jpg` — hexagon frame source, must stay next to app.py
- `vercel.json` — sets function timeout to 30s (image generation + 2 upstream API calls can take a few seconds)
- `.python-version` — pins Python 3.12

## Deploy (choose one)

### A) Vercel dashboard (easiest)
1. Push this folder's contents to a GitHub repo (root of the repo = these files).
2. On vercel.com → **Add New Project** → import that repo.
3. Vercel auto-detects Flask from `requirements.txt` + the `app = Flask(__name__)` in `app.py`. No other settings needed.
4. Deploy.

### B) Vercel CLI
```bash
npm i -g vercel
cd this-folder
vercel        # preview deploy
vercel --prod # production deploy
```

## After deploy
Your endpoint will be:
```
https://<your-project>.vercel.app/player-outfit?uid=10609031393
```
and the status check:
```
https://<your-project>.vercel.app/
```

## Important notes for Vercel specifically
- Vercel's filesystem is **read-only** except `/tmp`. This app only *reads* `banner_template.jpg` and never writes to disk, so it's fine as-is.
- `fonts/` folder is not included — the app automatically falls back to its built-in bitmap font if no TTF is found, so text still renders fine without it. If you want the nicer Poppins font, add a `fonts/` folder with `Poppins-Bold.ttf` and `Poppins-Medium.ttf` next to `app.py` before deploying.
- Each request calls two external APIs (player info + icons) — cold starts plus those calls mean the first request after idle time can take a couple of seconds longer. `maxDuration: 30` in `vercel.json` gives it room.
- In-memory caches (`lru_cache`, the static banner background) reset whenever Vercel spins up a new serverless instance — this is normal/expected on serverless, not a bug.
- Do **not** deploy `app.pyc` to Vercel — Vercel's zero-config Flask detection reads the source text of `app.py` to find the `Flask` instance, so it needs the real `.py` file, not compiled bytecode.
