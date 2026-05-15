from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.mcp import router as mcp_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()

app = FastAPI(
    title="companycrawler API",
    description=(
        "Companycrawler verzamelt publiek toegankelijke website-informatie voor bedrijfsverkenning, "
        "salesvoorbereiding en PoC-scenario's. De API beheert websites, start en bewaakt crawls, "
        "ontsluit gevonden documenten en chunks, voert semantische zoekopdrachten uit en start de "
        "agentische analyseketen die bedrijfsprofiel, uitdagingen, waardekansen, marktcontext en "
        "technologische aanknopingspunten samenvat. Dezelfde datacontracten voeden de webconsole, "
        "Swagger/OpenAPI en de MCP-server, zodat UI, API-clients en LLM-tools dezelfde regels en "
        "context gebruiken."
    ),
    version="1.0.0",
    contact={"name": "Smawa"},
    openapi_tags=[
        {"name": "default", "description": "Operationele Companycrawler API voor websites, scans, documenten, analyse, gebruikers en instellingen."},
        {"name": "MCP", "description": "MCP manifest en JSON-RPC transport voor LLM-clients die dezelfde crawl- en analysedata gebruiken."},
    ],
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

