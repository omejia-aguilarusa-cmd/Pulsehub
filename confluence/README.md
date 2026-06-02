Confluence — verified, no‑fluff markets bot (stocks & crypto)

Not investment advice. For research and educational use only.

Quickstart
- Create venv: `python -m venv .venv && source .venv/bin/activate`
- Install: `pip install -r requirements.txt` (or `poetry install` if you prefer Poetry)
- Copy env: `cp .env.example .env` and fill keys
- Run API: `uvicorn confluence.api.server:app --reload`
- CLI: `python -m confluence.cli.main scan`

Safety & Compliance
- No passwords. API keys only; OS keyring recommended
- Robinhood equities: text order tickets only; no execution
- Robinhood Crypto: official API only (disabled until configured)
- Binance/Binance.US: official REST/WS, HMAC signing, rate‑limit aware

