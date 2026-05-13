import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import AnalysisPrompt, Website
from app.services.analysis import AnalysisService, seed_default_analysis_prompts


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def test_seed_default_analysis_prompts(db_session) -> None:
    seed_default_analysis_prompts(db_session)

    prompts = db_session.query(AnalysisPrompt).order_by(AnalysisPrompt.sort_order).all()
    prompt_ids = {prompt.prompt_id for prompt in prompts}

    assert "general_instruction" in prompt_ids
    assert "job_1_code_fields" in prompt_ids
    assert "job_9_technologie_indicaties" in prompt_ids


def test_render_prompt_replaces_company_variables(db_session) -> None:
    service = AnalysisService(db_session)

    rendered = service._render_prompt(
        "{{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in {{Regio}}",
        {"Bedrijfsnaam": "Acme", "Bedrijfsplaats": "Utrecht", "Regio": "Midden-Nederland"},
    )

    assert rendered == "Acme uit Utrecht in Midden-Nederland"


@pytest.mark.asyncio
async def test_run_company_analysis_stores_all_jobs(db_session, monkeypatch) -> None:
    seed_default_analysis_prompts(db_session)
    website = Website(url="https://example.com", company_name="Example", logo_url="")
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)

    async def fake_complete(self, prompt: str, max_tokens: int = 1400) -> str:
        if "Wat is de naam, de woonplaats en regio" in prompt:
            return '{"Bedrijfsnaam":"Example","Bedrijfsplaats":"Amsterdam","Regio":"Noord-Holland"}'
        return '{"samenvatting":"Analyse klaar","bewijsniveau":"bron"}'

    async def fake_embed(self, text: str) -> list[float]:
        return [0.1] * 1536

    monkeypatch.setattr("app.services.ai.AIService.complete", fake_complete)
    monkeypatch.setattr("app.services.ai.AIService.embed", fake_embed)

    run = await AnalysisService(db_session).run_company_analysis(website.id)

    assert run.status == "completed"
    assert len(run.job_results) == 9
    assert '"Bedrijfsplaats": "Amsterdam"' in run.extracted_variables
