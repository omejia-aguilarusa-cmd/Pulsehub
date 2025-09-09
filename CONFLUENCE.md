# Confluence (Python)

This directory provides a Python 3.11 codebase for "Confluence" — a verified, no‑fluff markets bot for stocks and crypto.

Highlights
- Async core with FastAPI, APScheduler, httpx, and websockets
- Verification across ≥2 independent data sources before emitting signals
- Strict compliance: no passwords, Robinhood equities = text tickets only; Binance REST/WS with HMAC
- JSON signal schema, terse logs, journaling via SQLite (upgradeable to Postgres)

Quickstart
- Configure `config/config.yml` and (optionally) `config/.env`
- Install with Poetry: `poetry install`
- One‑off scan: `poetry run python -m confluence.cli scan day`
- API server: `poetry run python -m confluence.cli server`
- Scheduler: `poetry run python -m confluence.cli schedule`

Security & Secrets
- API keys via environment or OS keyring; no secrets in repo
- Robinhood Crypto execution is disabled unless official API keys are configured (no unofficial endpoints)

