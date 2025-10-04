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

## Backend setup (uv)

This project uses [uv](https://github.com/astral-sh/uv) so you don’t have to manage Python virtualenvs manually.

Install dependencies and start the API in one shot:

```bash
uv run --with backend/requirements_api.txt -- python -m backend.api_server
```

`uv` caches the environment under the hood; repeat runs are instant. The server listens on `http://localhost:5000`.

### CLI workflow

You can exercise the full recommendation pipeline from the CLI:

```bash
python run.py --no-expansion --top 10
```

The command streams stage updates while it queries Spotify/MusicBrainz/AcousticBrainz and Claude. Expect ~1–3 minutes on the first run because of external APIs and caching warm‑up.

## Frontend setup

From the repo root:

```bash
npm install          # installs npm-run-all and bootstraps frontend deps
npm run setup        # installs frontend dependencies (runs npm --prefix frontend install)
npm run dev          # starts backend (via uv) and frontend concurrently
```

`npm run dev` launches the Vite dev server on `http://localhost:3000` with a proxy to `http://localhost:5000`, and starts the Flask API via `uv run ...`. Stop both with `Ctrl+C`.

You can also run the pieces individually:

```bash
npm run backend    # uv-run Flask API only
npm run frontend   # frontend dev server only
```

When both services are up:

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
