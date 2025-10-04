# HackathonBestTeam

Full‑stack prototype that turns a handful of artist swipes into underground recommendations.

## Prerequisites

- Python 3.9+
- Node.js 18+ and npm
- Spotify API credentials (client id/secret)
- Anthropic Claude API key (used for taste profiling + subjective embeddings)

Create a `.env` in the repo root next to `run.py`:

```
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
CLAUDE_API_KEY=...
```

This file is git‑ignored; keep it local.

## Backend setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements_api.txt
```

Start the API:

```bash
python -m backend.api_server
```

The Flask server listens on `http://localhost:5000`.

### CLI workflow

You can exercise the full recommendation pipeline from the CLI:

```bash
python run.py --no-expansion --top 10
```

The command streams stage updates while it queries Spotify/MusicBrainz/AcousticBrainz and Claude. Expect ~1–3 minutes on the first run because of external APIs and caching warm‑up.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server boots on `http://localhost:3000` and proxies `/api/*` calls to the Flask backend (see `frontend/vite.config.js`). When both services are up:

1. Swipe through the seeded “popular artists”.
2. The frontend posts each rating to `/api/rate-artist` (logged server‑side) and, once done, sends the entire set to `/api/recommendations`.
3. The Flask API calls into `generate_candidates`/`rank_candidates` and returns a ranked list with diagnostics.

## Project structure

```
backend/
  api_server.py      # Flask HTTP layer
  candidates_gen.py  # Spotify discovery, dedupe, filtering
  filter_candidates.py  # Embeddings, scoring, diversity pass
  services.py        # Spotify + AcousticBrainz + Claude clients
frontend/
  src/               # React UI (Vite)
tests/               # pytest unit + integration + live checks
run.py               # CLI driver for manual testing
impl_plan.md         # Implementation notes
```

## Notes

- The backend caches MusicBrainz/AcousticBrainz lookups and Claude responses in memory; restart the server to clear.
- Spotify’s API can throw `429 Too Many Requests`; automatic retry with `Retry-After` is built in, but rapid repeated requests may still block temporarily.
- Claude model `claude-3-5-sonnet-20241022` is marked for deprecation in Oct 2025—swap the model ids in `services.py` when Anthropic updates the lineup.
