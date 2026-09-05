# Lead Hunter OS

Stage 1 foundation for a multi-tenant lead discovery, campaign, messaging and publication operations system. The domain is platform-neutral; Telegram is represented by an adapter boundary and is disabled for real sending by default.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Admin panel: http://localhost:3000
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Demo login: `demo@leadhunter.local` / `demo-password`

Local backend without Docker (requires Python 3.12 and dependencies):

```bash
pip install -e '.[dev]'
$env:DATABASE_URL='sqlite:///./lead_hunter_test.db'  # isolated local/test use only
python -m app.seed
uvicorn app.main:app --reload --app-dir backend
```

## Commands

```bash
alembic -c alembic.ini upgrade head
python -m app.seed
pytest
ruff check backend
mypy backend/app
cd frontend; npm install; npm run typecheck; npm run build
```

See `docs/` for architecture, security, policy, queue, operations and next-stage decisions.

All modules and operational reports are governed by [`GLOBAL_EXECUTION_PROTOCOL.md`](GLOBAL_EXECUTION_PROTOCOL.md). It has maximum project priority: unverified state must never be reported as completed.

## Manual Telegram dialog triage

Open `Triage` in the admin panel to review Telegram dialogs in deterministic batches. The default batch is 30 and the queue contains only `UNREVIEWED` dialogs. Manual type, eligibility, collections, tags and notes are saved transactionally with optimistic locking; AI metadata is advisory only. Telegram real send, joins and Telegram folder writes remain disabled.

Stage 3.2.2 makes this an interactive flow: the next batch opens automatically after save, keyboard shortcuts are available, affected Community Dataset/Campaign Intelligence records refresh incrementally, and a completion summary appears at the end. See `docs/INTERACTIVE_OPERATOR_REVIEW.md`.
