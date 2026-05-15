import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import AnalysisInsight, AnalysisJobResult, AnalysisPrompt, AnalysisRun, ContentChunk, Document, ScanJob, Website
from app.services.crawler import CompanyCrawler
from app.services import crawler as crawler_module
from app.api.routes import _scan_duration_seconds
from app.schemas.dto import ProviderSettingsUpdate


def test_canonical_host_ignores_www_prefix() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._canonical_host("https://www.darbouwadvies.nl/") == "darbouwadvies.nl"
    assert crawler._canonical_host("https://darbouwadvies.nl/over-ons/") == "darbouwadvies.nl"


def test_normalize_url_removes_fragments_but_keeps_path_trailing_slash() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._normalize_url("https://darbouwadvies.nl/contact/#content") == "https://darbouwadvies.nl/contact/"
    assert crawler._normalize_url("https://darbouwadvies.nl/") == "https://darbouwadvies.nl"


def test_canonical_url_ignores_www_and_fragments() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._canonical_url("HTTPS://www.darbouwadvies.nl/#content") == "https://darbouwadvies.nl"
    assert crawler._canonical_url("https://www.darbouwadvies.nl/contact/#top") == "https://darbouwadvies.nl/contact/"


def test_canonical_url_does_not_convert_mailto_to_https_url() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._canonical_url("mailto:thijmen@darbouwadvies.nl/over-ons/algemene-informatie/") == "mailto:thijmen@darbouwadvies.nl/over-ons/algemene-informatie/"
    assert not crawler._is_crawlable_url("mailto:thijmen@darbouwadvies.nl/over-ons/algemene-informatie/")


def test_detect_logo_url_prefers_declared_icons() -> None:
    crawler = object.__new__(CompanyCrawler)
    html = """
    <html><head><link rel="apple-touch-icon" href="/apple.png"></head>
    <body><img src="/brand-logo.svg" alt="Company logo"></body></html>
    """

    assert crawler._detect_logo_url("https://example.com/home", html) == "https://example.com/apple.png"


def test_detect_logo_url_falls_back_to_logo_image() -> None:
    crawler = object.__new__(CompanyCrawler)
    html = '<html><body><img src="/assets/company-logo.svg" alt="Company logo"></body></html>'

    assert crawler._detect_logo_url("https://example.com", html) == "https://example.com/assets/company-logo.svg"


def test_parse_company_profile_accepts_json_and_dutch_keys() -> None:
    from app.services.ai import AIService

    ai = object.__new__(AIService)

    assert ai._parse_company_profile('{"Bedrijfsnaam":"Smawa","Bedrijfsplaats":"Amsterdam","Regio":"Noord-Holland"}') == {
        "company_name": "Smawa",
        "company_place": "Amsterdam",
        "region": "Noord-Holland",
    }


def test_content_hash_normalizes_whitespace_and_case() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._content_hash("Contact  test@example.com") == crawler._content_hash(" contact\nTEST@example.com ")


def test_extract_mailto_addresses_keeps_emails_available_for_vectors() -> None:
    crawler = object.__new__(CompanyCrawler)
    soup = BeautifulSoup(
        """
        <html><body>
          <a href="mailto:info@example.com?subject=Hallo">Mail ons</a>
          <a href="mailto:sales@example.com;support@example.com">Team</a>
          <a href="mailto:INFO@example.com">Dubbel</a>
          <a href="tel:+31123456789">Bel ons</a>
        </body></html>
        """,
        "html.parser",
    )

    assert crawler._extract_mailto_addresses(soup) == [
        "info@example.com",
        "sales@example.com",
        "support@example.com",
    ]


def make_scan_session() -> tuple[Session, Website, ScanJob]:
    engine = create_engine("sqlite:///:memory:")
    Website.__table__.create(bind=engine)
    ScanJob.__table__.create(bind=engine)
    db = Session(engine)
    website = Website(url="https://example.com", company_name="Example")
    db.add(website)
    db.commit()
    scan = ScanJob(website_id=website.id, started_at=datetime.utcnow())
    db.add(scan)
    db.commit()
    db.refresh(website)
    db.refresh(scan)
    return db, website, scan


def make_graph_session() -> tuple[Session, Website, ScanJob, Document, ContentChunk]:
    engine = create_engine("sqlite:///:memory:")
    Website.__table__.create(bind=engine)
    ScanJob.__table__.create(bind=engine)
    Document.__table__.create(bind=engine)
    ContentChunk.__table__.create(bind=engine)
    AnalysisPrompt.__table__.create(bind=engine)
    AnalysisRun.__table__.create(bind=engine)
    AnalysisJobResult.__table__.create(bind=engine)
    AnalysisInsight.__table__.create(bind=engine)
    db = Session(engine)
    website = Website(url="https://example.com", company_name="Example")
    db.add(website)
    db.commit()
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    document = Document(website_id=website.id, scan_id=scan.id, source_url="https://example.com")
    db.add(document)
    db.commit()
    chunk = ContentChunk(document_id=document.id, chunk_index=0, text="hello", embedding="[]")
    db.add(chunk)
    prompt = AnalysisPrompt(prompt_id="job_1_code_fields", title="Code fields")
    db.add(prompt)
    db.commit()
    run = AnalysisRun(website_id=website.id, status="completed")
    db.add(run)
    db.commit()
    job = AnalysisJobResult(analysis_run_id=run.id, prompt_id=prompt.prompt_id, status="completed", result_text="klaar")
    insight = AnalysisInsight(analysis_run_id=run.id, website_id=website.id, prompt_id=prompt.prompt_id, text="klaar")
    db.add_all([job, insight])
    db.commit()
    return db, website, scan, document, chunk


@pytest.mark.asyncio
async def test_crawl_queue_deduplicates_links_and_stops_cycles(monkeypatch) -> None:
    db, website, scan = make_scan_session()
    crawler = CompanyCrawler.__new__(CompanyCrawler)
    crawler.db = db
    crawler.settings = SimpleNamespace(scan_max_items=20, scan_max_depth=5, scan_max_parallel_items=2)
    crawler.robots = {}
    calls: list[str] = []

    async def fake_process(_semaphore, _client, _website_id, _scan_id, url, depth):
        calls.append(url)
        if url == "https://example.com":
            links = [
                "https://example.com/about#team",
                "https://www.example.com/about#other",
                "https://example.com/contact",
                "mailto:info@example.com/contact",
            ]
        elif url == "https://example.com/about":
            links = ["https://example.com", "https://example.com/contact#form"]
        else:
            links = ["https://example.com/about"]
        return crawler_module.ProcessedContent(url, url, depth, links, stored=True)

    monkeypatch.setattr(crawler, "_process_url", fake_process)

    await crawler._crawl_website(website, scan)

    assert calls.count("https://example.com/about") == 1
    assert calls.count("https://example.com/contact") == 1
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_crawl_respects_parallel_limit(monkeypatch) -> None:
    db, website, scan = make_scan_session()
    crawler = CompanyCrawler.__new__(CompanyCrawler)
    crawler.db = db
    crawler.settings = SimpleNamespace(scan_max_items=8, scan_max_depth=2, scan_max_parallel_items=2)
    crawler.robots = {}
    active = 0
    max_active = 0

    async def fake_process(_semaphore, _client, _website_id, _scan_id, url, depth):
        nonlocal active, max_active
        async with _semaphore:
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
        links = [f"https://example.com/page-{index}" for index in range(5)] if depth == 0 else []
        return crawler_module.ProcessedContent(url, url, depth, links, stored=True)

    monkeypatch.setattr(crawler, "_process_url", fake_process)

    await crawler._crawl_website(website, scan)

    assert max_active <= 2


def test_scan_duration_uses_completed_at_when_available() -> None:
    scan = ScanJob(
        website_id=1,
        started_at=datetime(2026, 5, 13, 10, 0, 0),
        completed_at=datetime(2026, 5, 13, 11, 2, 3),
    )

    assert _scan_duration_seconds(scan) == 3723


def test_crawl_setting_validation_rejects_zero() -> None:
    with pytest.raises(ValueError):
        ProviderSettingsUpdate(scan_max_items=0)


def test_reset_deletes_documents_scans_graph_chunks_and_analyses() -> None:
    from app.api.routes import reset_website

    db, website, _scan, _document, _chunk = make_graph_session()

    assert reset_website(website.id, db) == {"status": "reset"}
    assert db.query(ContentChunk).count() == 0
    assert db.query(Document).count() == 0
    assert db.query(ScanJob).count() == 0
    assert db.query(AnalysisRun).count() == 0
    assert db.query(AnalysisJobResult).count() == 0
    assert db.query(AnalysisInsight).count() == 0
    assert db.query(AnalysisPrompt).count() == 1
    assert db.query(Website).count() == 1
