from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.mcp import router as mcp_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()

app = FastAPI(
    title="companycrawler API",
    description="API for public company website crawling, AI summaries, embeddings, Swagger and MCP access.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url, "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(mcp_router)


@app.on_event("startup")
def startup() -> None:
    init_db()

