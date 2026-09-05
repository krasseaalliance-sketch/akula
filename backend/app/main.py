from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import text

from .analytics_api import router as analytics_router
from .api import router
from .campaign_intelligence_api import router as campaign_intelligence_router
from .community_classification_api import router as community_classification_router
from .config import get_settings
from .constructive_api import router as constructive_router
from .customer_product import router as customer_product_router
from .db import engine
from .dialog_triage_api import router as dialog_triage_router
from .human_writing_api import router as human_writing_router
from .lead_intelligence_api import router as intelligence_router
from .service_control_api import router as service_control_router
from .support_api import router as support_router
from .telegram_api import router as telegram_router

app = FastAPI(
    title="Lead Hunter OS API", version="0.1.0", description="Multi-tenant campaign operations API"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(telegram_router)
app.include_router(intelligence_router)
app.include_router(campaign_intelligence_router)
app.include_router(dialog_triage_router)
app.include_router(analytics_router)
app.include_router(community_classification_router)
app.include_router(human_writing_router)
app.include_router(service_control_router)
app.include_router(customer_product_router)
app.include_router(support_router)
app.include_router(constructive_router)


@app.on_event("startup")
def startup() -> None:
    if (
        get_settings().app_env.lower() == "production"
        and get_settings().jwt_secret == "change-me-in-a-secret-store"
    ):
        raise RuntimeError("JWT_SECRET must be configured in production")


@app.get("/health")
def health():
    return {"status": "ok", "service": "backend"}


@app.get("/ready")
def ready():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    try:
        Redis.from_url(get_settings().redis_url).ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Queue unavailable") from exc
    return {"status": "ready", "database": "ok", "queue": "redis-ready"}


@app.get("/metrics")
def metrics():
    return {
        "service": "lead-hunter-api",
        "metrics": {
            "queue_backend": "postgres+redis",
            "publication_mode": get_settings().publication_mode,
        },
    }
