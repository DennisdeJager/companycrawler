import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.api.routes import delete_analysis, delete_analysis_job_result
from app.models import AnalysisInsight, AnalysisJobResult, AnalysisPrompt, AnalysisRun, Website
from app.services.ai import AIProviderError, AIService
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


def test_normalize_variables_ignores_unknown_company_name(db_session) -> None:
    service = AnalysisService(db_session)
    website = Website(url="https://example.com", company_name="Example BV", logo_url="")

    variables = service._normalize_variables(
        {"Bedrijfsnaam": "onbekend", "Bedrijfsplaats": "niet gevonden", "Regio": "Noord-Holland"},
        website,
    )

    assert variables == {"Bedrijfsnaam": "Example BV", "Bedrijfsplaats": "onbekend", "Regio": "Noord-Holland"}


def test_parse_json_returns_none_for_malformed_model_json(db_session) -> None:
    service = AnalysisService(db_session)
    malformed = """
    Hier is de analyse:
    {
      "bedrijf": "Example",
      "uitdagingen": [
        {"titel": "Administratie"}
      ]
      "samenvatting": "Mist een komma"
    }
    """

    assert service._parse_json(malformed) is None


def test_parse_json_extracts_balanced_object_from_markdown(db_session) -> None:
    service = AnalysisService(db_session)
    text = """```json
    {"Bedrijfsnaam":"Example","notitie":"tekst met } in string"}
    ```
    Extra toelichting.
    """

    assert service._parse_json(text)["Bedrijfsnaam"] == "Example"


def test_extract_responses_text_supports_output_content(db_session) -> None:
    service = AIService(db_session)

    text = service._extract_responses_text(
        {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "{\"Bedrijfsnaam\":\"Example\"}"},
                    ]
                }
            ]
        }
    )

    assert text == '{"Bedrijfsnaam":"Example"}'


@pytest.mark.asyncio
async def test_complete_raises_when_configured_provider_fails(db_session, monkeypatch) -> None:
    service = AIService(db_session)
    service.last_provider_error = "OpenAI responses faalde met HTTP 401: invalid api key"

    async def empty_provider(_provider: str, _model: str, _prompt: str, max_tokens: int) -> str:
        return ""

    monkeypatch.setattr(service, "_provider_has_key", lambda _provider: True)
    monkeypatch.setattr(service, "_chat_provider", empty_provider)

    with pytest.raises(AIProviderError, match="invalid api key"):
        await service.complete("test")


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


def test_delete_analysis_job_result_removes_result_and_insight(db_session) -> None:
    seed_default_analysis_prompts(db_session)
    website = Website(url="https://example.com", company_name="Example", logo_url="")
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)
    run = AnalysisRun(website_id=website.id, status="completed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    job = AnalysisJobResult(analysis_run_id=run.id, prompt_id="job_2_bedrijfsprofiel", status="completed", result_text="klaar")
    insight = AnalysisInsight(analysis_run_id=run.id, website_id=website.id, prompt_id="job_2_bedrijfsprofiel", text="klaar")
    db_session.add_all([job, insight])
    db_session.commit()
    db_session.refresh(job)

    response = delete_analysis_job_result(job.id, db_session)

    assert response == {"status": "deleted"}
    assert db_session.get(AnalysisJobResult, job.id) is None
    assert db_session.query(AnalysisInsight).filter(AnalysisInsight.analysis_run_id == run.id).count() == 0


def test_delete_analysis_removes_jobs_and_insights(db_session) -> None:
    seed_default_analysis_prompts(db_session)
    website = Website(url="https://example.com", company_name="Example", logo_url="")
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)
    run = AnalysisRun(website_id=website.id, status="completed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    job = AnalysisJobResult(analysis_run_id=run.id, prompt_id="job_2_bedrijfsprofiel", status="completed", result_text="klaar")
    insight = AnalysisInsight(analysis_run_id=run.id, website_id=website.id, prompt_id="job_2_bedrijfsprofiel", text="klaar")
    db_session.add_all([job, insight])
    db_session.commit()

    response = delete_analysis(run.id, db_session)

    assert response == {"status": "deleted"}
    assert db_session.get(AnalysisRun, run.id) is None
    assert db_session.query(AnalysisJobResult).count() == 0
    assert db_session.query(AnalysisInsight).count() == 0
