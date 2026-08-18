# VC Investment Intelligence Platform — V1 (MVP)

An AI-native due-diligence platform for VC/growth-equity investors. You upload a pitch
deck; the platform does not summarize it — it independently extracts, researches,
verifies, challenges, benchmarks and reasons about the claims inside it, and produces
a sourced investment memo you can drill into, conclusion by conclusion, down to the
underlying evidence.

Core philosophy, enforced in the code, not just the prompt:

```
Extract -> Research -> Verify -> Challenge -> Benchmark -> Reason -> Conclude
```

Every number that reaches the screen traces back to a row in the `evidence` table
with an explicit **origin** (company claim / external source / platform calculation /
platform inference / unknown), a **confidence level**, and — wherever applicable — a
source URL and a methodology string. Nothing is presented as verified unless it is.

## What's real in this repo

This is not a mockup. Both services are implemented and tested end-to-end:

- **Backend** (`backend/`, FastAPI + SQLAlchemy): a working REST API with a real
  Postgres/SQLite-backed evidence store, a deterministic calculation engine (TAM
  bottom-up/top-down, CAGR, NRR/GRR, CAC payback, LTV, Rule of 40, MRR-volatility
  detection, CAC/LTV consistency checking), real `.pptx`/`.pdf` parsing, and four
  reasoning modules (Market, Competition, Traction, Founders) that each run a real
  extract → research → verify → calculate → benchmark pipeline against external
  providers (Anthropic Claude for reasoning/extraction, Tavily for web research,
  Pappers.fr for French company/founder registry data).
- **Frontend** (`frontend/`, Next.js + TypeScript): the "tray" dashboard, per-module
  drill-down (conclusion → reasoning trace → evidence trail → source), the
  human-in-the-loop recalculation forms, and the investment memo view.
- **31 backend unit/integration tests**, all passing, including a full pipeline run
  in mock mode and a real end-to-end browser test (Playwright) driving the actual UI
  against the actual API.

**Mock mode:** every external provider (Anthropic, Tavily, Pappers.fr) is optional at
boot. Without API keys, the whole app still runs end-to-end — every mock-mode output
is explicitly labelled `mode: "mock"` and carries `confidence: unverified` rather than
being silently presented as a real finding. This is what let the pipeline be built and
tested without live keys, and it's also a legitimate product behavior: better to say
"unable to independently verify" than to fabricate.

## Scope of this V1 (by design, not by accident)

We deliberately scoped down from the full 55-section product spec to something that
could be built for real and validated end-to-end, rather than a shallow pass over
everything. Agreed scope for this build:

- **Business model:** SaaS only. The rule library (`backend/app/rules/`) and the
  traction module's metrics (ARR/MRR, NRR/GRR, CAC/LTV, Rule of 40) are SaaS-specific.
  Marketplace/hardware/deeptech frameworks are Phase 3.
- **Modules implemented:** Market, Competition & Moat, Traction & Business Model,
  Team/Founders, Red Flags, Investment Memo.
- **Modules NOT yet implemented** (see Roadmap): Valuation & Return/Exit scenarios,
  three-scenario financial modeling (Management/Base/Downside/Upside), Historical
  Reality Check / comparable-outcomes database, "Ask the Deal" conversational
  interface, Deal Database / institutional memory, fund-specific constraint engine,
  Legal/IP module.

## Known limitations (read before demoing to anyone)

- **Deck value parsing is regex-based.** `parse_money()` handles common formats
  ("EUR 10bn", "$2.5M") but chart data embedded as images/graphs is not read — MRR
  series and other chart-only figures must be entered manually via the human-in-the-loop
  forms (`/traction/mrr-series`, `/market/recalculate`).
- **Pappers.fr only covers French legal entities.** Non-French companies will show
  "not found" on the founders module until a second provider is added.
- **No paid market-intelligence data sources are wired up** (Crunchbase, PitchBook,
  CB Insights, G2/Capterra). Research quality is bounded by what Tavily's web search
  surfaces. This is an intentional MVP trade-off agreed with the product owner.
- **Analysis runs synchronously on upload.** In live mode (real API keys), uploading
  a deck can take 30–90 seconds while the four modules run their research passes.
  There's no background job queue yet — that's the first thing to add before this
  goes in front of real users at any volume.
- **No authentication / multi-tenancy.** Anyone with API access can see all companies.
  Add auth before deploying anywhere but a local machine.
- **`create_all()`, not migrations.** Schema changes during development will require
  dropping the dev database. Add Alembic before the schema needs to evolve in
  production with real data in it.

## Quickstart (local, no Docker)

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in API keys, or leave blank to run in mock mode
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` — you should see `{"status": "ok", ...}`.

Run the test suite:

```bash
pytest -v            # 31 tests, ~0.5s, no API keys required
python scripts/smoke_test.py   # full pipeline through the real HTTP API, mock mode
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL, defaults to localhost:8000
npm run dev
```

Visit `http://localhost:3000`, create a company, upload a `.pptx` or `.pdf` pitch deck.

## Quickstart (Docker Compose)

```bash
cp .env.example .env   # fill in API keys, or leave blank for mock mode
docker compose up --build
```

Backend on `http://localhost:8000`, frontend on `http://localhost:3000`, Postgres
persisted in a named volume.

## Getting API keys (all optional — the app runs in mock mode without them)

| Provider | Used for | Where to get a key |
|---|---|---|
| Anthropic | Extraction, research synthesis, contradiction/assumption reasoning | https://console.anthropic.com |
| Tavily | Web research (market, competition, traction, founder verification) | https://tavily.com |
| Pappers.fr | French company registry / founder background check | https://www.pappers.fr/api |

Set them in `.env` (see `.env.example`). `GET /health` reports which providers are
live vs. mock.

## Project structure

```
backend/
  app/
    models.py            # SQLAlchemy models - the evidence-based data model
    schemas.py            # Pydantic API schemas
    services/
      deck_parser.py       # .pptx / .pdf -> structured slide text (deterministic)
      llm_client.py         # Anthropic wrapper, mock-mode fallback for every method
      search_client.py      # Tavily wrapper, mock-mode fallback
      pappers_client.py     # Pappers.fr wrapper, mock-mode fallback
      evidence_store.py     # single choke point for writing Evidence rows
      calc/                # deterministic math: market sizing, SaaS metrics, parsing
      reasoning/            # the actual reasoning-loop modules (market/competition/traction/founders/memo)
    rules/                 # stage-aware + SaaS business-model rule library
    routers/                # FastAPI endpoints
  tests/                   # 31 tests: calc engine, parsing, deck parsing, full pipeline
  scripts/smoke_test.py    # end-to-end HTTP smoke test
frontend/
  app/                     # Next.js App Router pages (tray, module drill-down, memo)
  components/               # forms, badges, evidence/reasoning-trace renderers
  lib/api.ts                # typed API client
docker-compose.yml
DEPLOYMENT.md
```

## Roadmap (Phase 2 / Phase 3)

Phase 2 — Moat as a first-class module, Financial Reality Check + three-scenario
modeling (Management/Base/Downside/Upside), Valuation & Return/Exit analysis,
"Ask the Deal" (RAG chat over the evidence store already built in Phase 1), Deal
Database across companies, background job queue for analysis runs.

Phase 3 — Multi-business-model rule library (marketplace, hardware, deeptech, ...),
fund-specific constraint engine, Historical Reality Check / comparable-outcomes
database, Legal/IP module, additional data-source integrations (Crunchbase/Dealroom,
G2/Capterra, Similarweb), authentication and multi-tenancy.
