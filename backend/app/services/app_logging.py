from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppLog


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"GOCSPX-[A-Za-z0-9_\-]{8,}"),
]


def sanitize_log_text(value: str) -> str:
    clean = value or ""
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[redacted]", clean)
    return clean[:8000]


def log_event(
    db: Session,
    *,
    level: str,
    category: str,
    message: str,
    details: str | dict[str, Any] | list[Any] = "",
    website_id: int | None = None,
    analysis_run_id: int | None = None,
    analysis_job_result_id: int | None = None,
) -> AppLog:
    if not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    row = AppLog(
        level=level[:32],
        category=category[:64],
        message=sanitize_log_text(message)[:512],
        details=sanitize_log_text(details),
        website_id=website_id,
        analysis_run_id=analysis_run_id,
        analysis_job_result_id=analysis_job_result_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
