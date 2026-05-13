from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebsiteCreate(BaseModel):
    url: HttpUrl
    company_name: str = Field(min_length=1, max_length=255)


class WebsiteUpdate(BaseModel):
    url: HttpUrl | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=255)


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    company_name: str
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


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    source_url: str
    title: str
    content_type: str
    file_name: str
    storage_path: str
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
    google_required_origins: list[str]
    default_summary_provider: str
    default_summary_model: str
    default_embedding_provider: str
    default_embedding_model: str
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
