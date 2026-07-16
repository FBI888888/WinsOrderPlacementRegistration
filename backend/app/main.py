from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.funds.router import router as funds_router
from app.modules.iam.router import router as iam_router
from app.modules.orders.router import router as orders_router
from app.modules.partners.router import router as partners_router
from app.modules.points.router import router as points_router
from app.modules.reports.router import router as reports_router
from app.modules.settlements.router import router as settlements_router

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    iam_router,
    partners_router,
    orders_router,
    points_router,
    funds_router,
    settlements_router,
    reports_router,
):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok"}