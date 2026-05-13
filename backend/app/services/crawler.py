import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ContentChunk, Document, ScanJob, Website
from app.models.entities import ScanStatus
from app.services.ai import AIService, embedding_to_json


SUPPORTED_FILE_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".json", ".md"}


@dataclass
class FetchedContent:
    url: str
    title: str
    content_type: str
    text: str
    links: list[str]
    file_name: str = ""
    content: bytes = b""


class CompanyCrawler:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.ai = AIService(db)
        self.robots: dict[str, robotparser.RobotFileParser] = {}

    async def detect_company_name(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(str(url), headers={"User-Agent": "companycrawler/1.0 public marketing crawler"})
            response.raise_for_status()
            return await self.ai.detect_company_name(str(response.url), response.text)

    async def run_scan(self, scan_id: int) -> None:
        scan = self.db.get(ScanJob, scan_id)
        if not scan:
            return
        website = self.db.get(Website, scan.website_id)
        if not website:
            return
        scan.status = ScanStatus.running
        scan.started_at = datetime.utcnow()
        scan.message = "Crawler gestart"
        self.db.commit()

        try:
            await self._crawl_website(website, scan)
            scan.status = ScanStatus.completed
            scan.progress = 100
            scan.message = "Scan afgerond"
            scan.completed_at = datetime.utcnow()
            self.db.commit()
        except Exception as exc:
            scan.status = ScanStatus.failed
            scan.error = str(exc)
            scan.message = "Scan mislukt"
            scan.completed_at = datetime.utcnow()
            self.db.commit()

    async def _crawl_website(self, website: Website, scan: ScanJob) -> None:
        root = self._normalize_url(website.url)
        root_host = self._canonical_host(root)
        queue: list[tuple[str, int]] = [(root, 0)]
        seen: set[str] = set()

        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            while queue and len(seen) < self.settings.scan_max_items:
                current, depth = queue.pop(0)
                if current in seen or depth > self.settings.scan_max_depth:
                    continue
                if not await self._allowed_by_robots(client, current):
                    continue
                seen.add(current)
                scan.items_found = max(scan.items_found, len(seen) + len(queue))
                scan.message = f"Verwerkt {len(seen)} items"
                scan.progress = min(95, int((len(seen) / self.settings.scan_max_items) * 100))
                self.db.commit()

                fetched = await self._fetch(client, current)
                if not fetched or not fetched.text.strip():
                    continue
                final_url = self._normalize_url(fetched.url)
                seen.add(final_url)
                await self._store_document(website, scan, fetched)

                for link in fetched.links:
                    normalized = self._normalize_url(link)
                    parsed = urlparse(normalized)
                    if parsed.scheme not in {"http", "https"}:
                        continue
                    if self._canonical_host(normalized) != root_host:
                        continue
                    if normalized not in seen and len(seen) + len(queue) < self.settings.scan_max_items:
                        queue.append((normalized, depth + 1))

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> FetchedContent | None:
        response = await client.get(url, headers={"User-Agent": "companycrawler/1.0 public marketing crawler"})
        if int(response.headers.get("content-length", "0") or 0) > self.settings.scan_max_file_mb * 1024 * 1024:
            return None
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0].lower()
        parsed = urlparse(str(response.url))
        file_name = parsed.path.rsplit("/", 1)[-1]
        extension = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

        if "html" in content_type or extension in {"", ".html", ".htm"}:
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else parsed.netloc
            for item in soup(["script", "style", "noscript", "svg"]):
                item.decompose()
            links = [urljoin(str(response.url), anchor.get("href")) for anchor in soup.find_all("a", href=True)]
            text = soup.get_text(" ", strip=True)
            return FetchedContent(str(response.url), title, content_type or "text/html", text, links)

        if extension not in SUPPORTED_FILE_EXTENSIONS:
            return None
        text = self._extract_file_text(extension, response.content)
        return FetchedContent(str(response.url), file_name, content_type or "application/octet-stream", text, [], file_name=file_name, content=response.content)

    def _extract_file_text(self, extension: str, content: bytes) -> str:
        if extension == ".pdf":
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if extension == ".docx":
            doc = DocxDocument(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        return content.decode("utf-8", errors="ignore")

    async def _store_document(self, website: Website, scan: ScanJob, fetched: FetchedContent) -> None:
        summary, display_summary = await self.ai.summarize(fetched.title, fetched.text)
        document = (
            self.db.query(Document)
            .filter(Document.website_id == website.id, Document.source_url == fetched.url)
            .first()
        )
        if not document:
            document = Document(website_id=website.id, source_url=fetched.url)
            self.db.add(document)
        document.scan_id = scan.id
        document.title = fetched.title[:512]
        document.content_type = fetched.content_type[:128]
        document.file_name = fetched.file_name[:255]
        document.storage_path = self._store_file_bytes(website.id, fetched) if fetched.file_name else ""
        document.text_content = fetched.text
        document.summary = summary
        document.display_summary = display_summary[:280]
        document.vector_status = "processing"
        self.db.commit()
        self.db.refresh(document)

        self.db.query(ContentChunk).filter(ContentChunk.document_id == document.id).delete()
        for index, chunk_text in enumerate(self._chunk_text(fetched.text)):
            embedding = await self.ai.embed(chunk_text)
            self.db.add(
                ContentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    text=chunk_text,
                    embedding_vector=self._pgvector(embedding),
                    embedding=embedding_to_json(embedding),
                    embedding_model=self.settings.default_embedding_model,
                    score_hint=self._hash_score(chunk_text),
                )
            )
        document.vector_status = "ready"
        scan.items_processed += 1
        self.db.commit()
        await asyncio.sleep(0)

    def _chunk_text(self, text: str, size: int = 1200, overlap: int = 160) -> list[str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if not clean:
            return []
        chunks = []
        start = 0
        while start < len(clean):
            chunks.append(clean[start : start + size])
            start += size - overlap
        return chunks[:40]

    def _normalize_url(self, url: str) -> str:
        clean, _fragment = urldefrag(str(url))
        if not clean.startswith(("http://", "https://")):
            clean = "https://" + clean
        return clean.rstrip("/")

    def _canonical_host(self, url: str) -> str:
        host = urlparse(url).hostname or ""
        host = host.lower()
        return host[4:] if host.startswith("www.") else host

    async def _allowed_by_robots(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self.robots:
            parser = robotparser.RobotFileParser()
            parser.set_url(f"{root}/robots.txt")
            try:
                response = await client.get(f"{root}/robots.txt")
                parser.parse(response.text.splitlines() if response.status_code < 400 else [])
            except Exception:
                parser.parse([])
            self.robots[root] = parser
        return self.robots[root].can_fetch("companycrawler/1.0 public marketing crawler", url)

    def _store_file_bytes(self, website_id: int, fetched: FetchedContent) -> str:
        if not fetched.content:
            return ""
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", fetched.file_name)[:160] or "download.bin"
        digest = hashlib.sha256(fetched.url.encode("utf-8")).hexdigest()[:12]
        directory = os.path.join("storage", "websites", str(website_id))
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{digest}-{safe_name}")
        with open(path, "wb") as handle:
            handle.write(fetched.content)
        return path

    def _hash_score(self, text: str) -> float:
        digest = hashlib.sha256(text[:1000].encode("utf-8")).digest()
        return digest[0] / 255

    def _pgvector(self, embedding: list[float]) -> list[float]:
        vector = embedding[:1536]
        if len(vector) < 1536:
            vector.extend([0.0] * (1536 - len(vector)))
        return vector
