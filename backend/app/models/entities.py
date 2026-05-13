from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class UserRole(str, Enum):
    admin = "admin"
    user = "user"
    guest = "guest"


class ScanStatus(str, Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    stopped = "stopped"
    completed = "completed"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.guest)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    logo_url: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scans: Mapped[list["ScanJob"]] = relationship(back_populates="website", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="website", cascade="all, delete-orphan")


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), index=True)
    status: Mapped[ScanStatus] = mapped_column(SAEnum(ScanStatus), default=ScanStatus.queued, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(512), default="Queued")
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    website: Mapped[Website] = relationship(back_populates="scans")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("website_id", "source_url", name="uq_document_website_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scan_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="text/html")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    storage_path: Mapped[str] = mapped_column(String(512), default="")
    text_content: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    display_summary: Mapped[str] = mapped_column(String(280), default="")
    vector_status: Mapped[str] = mapped_column(String(64), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    website: Mapped[Website] = relationship(back_populates="documents")
    chunks: Mapped[list["ContentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding_vector: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding: Mapped[str] = mapped_column(Text, default="[]")
    embedding_model: Mapped[str] = mapped_column(String(255), default="")
    score_hint: Mapped[float] = mapped_column(Float, default=0.0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class AnalysisPrompt(Base):
    __tablename__ = "analysis_prompts"

    prompt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(String(512), default="")
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_system_prompt: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    model: Mapped[str] = mapped_column(String(255), default="")
    extracted_variables: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    website: Mapped[Website] = relationship()
    job_results: Mapped[list["AnalysisJobResult"]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")
    insights: Mapped[list["AnalysisInsight"]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")


class AnalysisJobResult(Base):
    __tablename__ = "analysis_job_results"
    __table_args__ = (UniqueConstraint("analysis_run_id", "prompt_id", name="uq_analysis_job_run_prompt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("analysis_prompts.prompt_id", ondelete="RESTRICT"), index=True)
    rendered_prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    result_text: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="job_results")
    prompt: Mapped[AnalysisPrompt] = relationship()


class AnalysisInsight(Base):
    __tablename__ = "analysis_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    evidence_level: Mapped[str] = mapped_column(String(64), default="")
    sources: Mapped[str] = mapped_column(Text, default="[]")
    embedding_vector: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding: Mapped[str] = mapped_column(Text, default="[]")
    embedding_model: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="insights")


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    best_for: Mapped[str] = mapped_column(String(512), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
