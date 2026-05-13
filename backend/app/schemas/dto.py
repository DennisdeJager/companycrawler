from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebsiteCreate(BaseModel):
    url: HttpUrl
    company_name: str = Field(min_length=1, max_length=255)
    logo_url: str = Field(default="", max_length=2048)


class WebsiteUpdate(BaseModel):
    url: HttpUrl | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    logo_url: str | None = Field(default=None, max_length=2048)


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    company_name: str
    logo_url: str
    created_at: datetime
    updated_at: datetime


class ScanCreate(BaseModel):
    website_id: int


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    status: str
    progress: int
    message: str
    items_found: int
    items_processed: int
    error: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int = 0
    normal_db_size_mb: float = 0
    vector_db_size_mb: float = 0
    scan_max_parallel_items: int = 1


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    source_url: str
    title: str
    content_type: str
    file_name: str
    storage_path: str
    text_hash: str
    summary: str
    display_summary: str
    vector_status: str
    created_at: datetime


class DocumentDetail(DocumentRead):
    text_content: str


class SearchRequest(BaseModel):
    website_id: int | None = None
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


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
    extracted_variables: dict[str, str] = {}
    error: str
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

class GoogleLoginRequest(BaseModel):
    credential: str


class ProviderSettingsRead(BaseModel):
    openai_configured: bool
    openrouter_configured: bool
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
    scan_max_items: int | None = Field(default=None, ge=1)
    scan_max_file_mb: int | None = Field(default=None, ge=1)
    scan_max_depth: int | None = Field(default=None, ge=1)
    scan_max_parallel_items: int | None = Field(default=None, ge=1)
