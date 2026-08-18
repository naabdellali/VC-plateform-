# Deployment

Three ways to run this, roughly in order of effort.

## 1. Local machine (development / demo)

See "Quickstart (local, no Docker)" in the README. Fine for trying the product or
demoing it on your own machine. Not meant to stay running unattended.

## 2. Docker Compose on a single VM

```bash
git clone <this-repo>
cd vc-intelligence-platform
cp .env.example .env   # fill in API keys
docker compose up --build -d
```

This gets you Postgres + backend + frontend on one machine. Put a reverse proxy
(Caddy or nginx) in front for TLS if this will be reachable from the internet, and
change `CORS_ORIGINS` in `.env` to your real frontend origin. This setup has **no
authentication** — do not expose it publicly without adding some (see README
"Known limitations").

## 3. Split hosting (recommended once this is more than a personal demo)

Backend and frontend scale and redeploy independently, which matters once you're
iterating on the reasoning modules faster than the UI.

**Backend** — any container host works (Render, Railway, Fly.io, a plain VM). Steps:
1. Provision a managed Postgres instance (Render/Railway/Supabase all offer one).
2. Deploy `backend/` as a Docker service (the included `Dockerfile` works as-is) or
   as a native Python service (`pip install -r requirements.txt`, start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
3. Set environment variables: `DATABASE_URL` (from your managed Postgres),
   `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `PAPPERS_API_KEY`, `CORS_ORIGINS` (your
   frontend's deployed URL), `SECRET_KEY` (generate a real random value).
4. First boot runs `init_db()` automatically (`Base.metadata.create_all`) — no
   migration step needed yet for a fresh database. If you evolve the schema later,
   add Alembic before you have production data to preserve.

**Frontend** — Vercel is the path of least resistance for Next.js:
1. Import the `frontend/` directory as a Vercel project (or point it at the repo
   with a root directory override).
2. Set `NEXT_PUBLIC_API_URL` to your deployed backend URL in Vercel's environment
   variables. Remember this is inlined at **build** time — redeploy after changing it.
3. Deploy. Vercel handles TLS/CDN for you.

Alternatively, `frontend/Dockerfile` builds a standalone container if you'd rather
keep both services on the same host/provider as the backend.

## Health check

`GET /health` on the backend returns which providers are live vs. mock — use it as
your platform's health/readiness probe, and as a quick way to confirm API keys
actually made it into the deployed environment:

```json
{"status": "ok", "llm_mode": "live", "search_mode": "live", "pappers_mode": "live"}
```

## Before this touches real deal data

- Add authentication (pitch decks and founder background checks are sensitive).
- Add the background job queue noted in the README so deck uploads don't block an
  HTTP request for 30–90 seconds in live mode (Celery/RQ + Redis, or a simple
  FastAPI `BackgroundTasks` call to start with).
- Turn on TLS everywhere (reverse proxy or your host's built-in TLS).
- Decide on a data-retention policy for uploaded decks and generated evidence
  before you're holding other people's confidential fundraising materials.
