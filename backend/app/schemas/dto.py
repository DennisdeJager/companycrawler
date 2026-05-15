from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebsiteCreate(BaseModel):
    url: HttpUrl = Field(description="Publieke start-URL van de website die binnen hetzelfde domein wordt gecrawld.")
    company_name: str = Field(min_length=1, max_length=255, description="Herkenbare bedrijfsnaam zoals die in UI, analyses en MCP-antwoorden wordt gebruikt.")
    company_place: str = Field(default="", max_length=255, description="Vestigingsplaats wanneer die bekend of gedetecteerd is.")
    region: str = Field(default="", max_length=255, description="Regio of marktgebied voor latere analyse- en segmentatiecontext.")
    logo_url: str = Field(default="", max_length=2048, description="Publieke logo-URL voor herkenning in de webconsole.")


class WebsiteUpdate(BaseModel):
    url: HttpUrl | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    company_place: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=2048)


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    company_name: str
    company_place: str
    region: str
    logo_url: str
    created_at: datetime
    updated_at: datetime


class ScanCreate(BaseModel):
    website_id: int = Field(description="ID van het website-record waarvoor een crawljob in de wachtrij wordt gezet.")


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    status: str = Field(description="Jobstatus: queued, running, paused, stopped, completed of failed.")
    progress: int = Field(description="Globale voortgang in procenten. Een crawl blijft onder 100 tot de job is afgerond.")
    message: str = Field(description="Menselijke voortgangstekst voor dashboards en MCP-clients.")
    items_found: int = Field(description="Aantal bekende URL's/documenten dat tijdens de crawl is ontdekt.")
    items_processed: int = Field(description="Aantal URL's/documenten dat succesvol of gecontroleerd is verwerkt.")
    error: str = Field(description="Niet-lege tekst met fatale fouten of overgeslagen URL's, zoals dode links. UI-clients mogen dit als tijdelijke notificatie tonen.")
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int = 0
    normal_db_size_mb: float = Field(default=0, description="Geschatte opslagruimte voor documentmetadata, tekst en samenvattingen in MB.")
    vector_db_size_mb: float = Field(default=0, description="Geschatte opslagruimte voor chunks en embeddings in MB.")
    scan_max_parallel_items: int = Field(default=1, description="Aantal parallelle crawlverwerkingen dat voor deze omgeving is geconfigureerd.")


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    source_url: str = Field(description="Canonieke URL van de gecrawlde pagina of het bestand.")
    title: str = Field(description="Titel of afgeleide bestandsnaam die in tree, graph en zoekresultaten wordt gebruikt.")
    content_type: str = Field(description="HTTP content-type of afgeleid documenttype.")
    file_name: str = Field(description="Bestandsnaam voor downloads of documenten; leeg bij normale HTML-pagina's.")
    storage_path: str
    text_hash: str
    summary: str = Field(description="AI-samenvatting of extract dat als analysecontext kan worden gebruikt.")
    display_summary: str = Field(description="Korte UI-vriendelijke samenvatting voor kaarten, inspector en graph nodes.")
    vector_status: str = Field(description="Embeddingstatus, bijvoorbeeld ready, pending, failed of duplicate.")
    created_at: datetime


class DocumentDetail(DocumentRead):
    text_content: str


class SearchRequest(BaseModel):
    website_id: int | None = Field(default=None, description="Optioneel websitefilter. Zonder filter zoekt de API in alle beschikbare crawlcontent.")
    query: str = Field(min_length=1, description="Semantische vraag of zoekintentie, bijvoorbeeld een markt-, product- of technologiehaakje.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum aantal resultaten. Houd dit laag voor LLM-context en hoger voor UI-verkenning.")


class SearchResult(BaseModel):
    document_id: int
    website_id: int
    company_name: str
    source_url: str
    title: str
    summary: str
    content_type: str
    score: float


class AnalysisPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prompt_id: str
    title: str
    description: str
    prompt_text: str
    sort_order: int
    is_system_prompt: bool
    updated_at: datetime


class AnalysisPromptUpdate(BaseModel):
    prompt_text: str = Field(min_length=1)


class AnalysisJobResultRead(BaseModel):
    id: int
    prompt_id: str
    status: str
    summary: str
    result_text: str
    result_json: dict | list | str | int | float | bool | None = None
    sources: list[dict] = []
    error: str
    completed_at: datetime | None = None


class AnalysisRunRead(BaseModel):
    id: int
    website_id: int
    status: str
    model: str
    extracted_variables: dict[str, str] = Field(default={}, description="Gestructureerde bedrijfsvariabelen zoals naam, plaats en regio die de analyseketen gebruikt.")
    error: str = Field(description="Fouttekst wanneer de analyseketen of een onderliggende provider faalt.")
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    jobs: list[AnalysisJobResultRead] = []


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    model: str
    purpose: str
    best_for: str
    is_default: bool
    is_available: bool


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=255)
    role: str = "guest"
    is_active: bool = True


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=255)
    role: str | None = None
    is_active: bool | None = None


class GoogleLoginRequest(BaseModel):
    credential: str


class ProviderSettingsRead(BaseModel):
    openai_configured: bool
    openrouter_configured: bool
    openai_key_preview: str
    openrouter_key_preview: str
    google_auth_enabled: bool
    google_client_secret_configured: bool
    google_client_id: str
    app_url: str
    app_url_origin: str
    google_redirect_uri: str
    google_authorized_domains: list[str]
    default_summary_provider: str
    default_summary_model: str
    default_embedding_provider: str
    default_embedding_model: str
    default_agent_provider: str
    default_agent_model: str
    scan_max_items: int
    scan_max_file_mb: int
    scan_max_depth: int
    scan_max_parallel_items: int
    warnings: list[str]


class ProviderSettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    default_summary_provider: str | None = None
    default_summary_model: str | None = None
    default_embedding_provider: str | None = None
    default_embedding_model: str | None = None
    default_agent_provider: str | None = None
    default_agent_model: str | None = None
    scan_max_items: int | None = Field(default=None, ge=1)
    scan_max_file_mb: int | None = Field(default=None, ge=1)
    scan_max_depth: int | None = Field(default=None, ge=1)
    scan_max_parallel_items: int | None = Field(default=None, ge=1)


class AppLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    category: str
    message: str
    details: str
    website_id: int | None = None
    analysis_run_id: int | None = None
    analysis_job_result_id: int | None = None
    created_at: datetime
