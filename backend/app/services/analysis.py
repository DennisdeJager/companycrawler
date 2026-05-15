from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnalysisInsight, AnalysisJobResult, AnalysisPrompt, AnalysisRun, ContentChunk, Document, Website
from app.services.ai import AIService, embedding_from_json, embedding_to_json
from app.services.search import cosine


DEFAULT_ANALYSIS_PROMPTS: list[dict[str, Any]] = [
    {
        "prompt_id": "general_instruction",
        "title": "Algemene instructie voor alle jobs",
        "description": "Wordt toegevoegd aan jobs 2 t/m 9.",
        "sort_order": 0,
        "is_system_prompt": True,
        "prompt_text": """Je analyseert het bedrijf {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik primair de beschikbare bedrijfswebsite-content, documenten, metadata en eventuele gevonden bronfragmenten. Vul ontbrekende informatie alleen aan met voorzichtige LLM-redenering als dat duidelijk als aanname of waarschijnlijkheid wordt gemarkeerd.

Maak onderscheid tussen:
1. Feiten uit bronnen
2. Waarschijnlijke conclusies op basis van bronnen
3. AI-verrijking of hypothese zonder directe bron

Noem geen informatie als feit wanneer die niet in de bronnen staat. Geef per bevinding waar mogelijk een korte onderbouwing. Houd de output praktisch bruikbaar voor sales, prospecting en voorbereiding van een pilotgesprek door Smawa.""",
    },
    {
        "prompt_id": "job_1_code_fields",
        "title": "Job 1: Codevelden bepalen",
        "description": "Bepaalt Bedrijfsnaam, Bedrijfsplaats en Regio voor de volgende jobs.",
        "sort_order": 1,
        "is_system_prompt": False,
        "prompt_text": "Wat is de naam, de woonplaats en regio van dit bedrijf.\n\nGeef alleen JSON terug met exact deze keys: Bedrijfsnaam, Bedrijfsplaats, Regio.",
    },
    {
        "prompt_id": "job_2_bedrijfsprofiel",
        "title": "Job 2: Bedrijfsprofiel",
        "description": "Maakt een kort bedrijfsprofiel.",
        "sort_order": 2,
        "is_system_prompt": False,
        "prompt_text": "Maak een kort bedrijfsprofiel voor {{Bedrijfsnaam}} in {{Bedrijfsplaats}} in de regio {{Regio}}.",
    },
    {
        "prompt_id": "job_3_uitdagingen",
        "title": "Job 3: Uitdagingen",
        "description": "Belangrijkste waarschijnlijke knelpunten inclusief onderbouwing.",
        "sort_order": 3,
        "is_system_prompt": False,
        "prompt_text": """Analyseer de belangrijkste waarschijnlijke uitdagingen, knelpunten en risico’s voor {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik hiervoor de beschikbare bedrijfswebsite-content, dienstenpagina’s, vacatures, documenten, PDF’s, cases, contactpagina’s en andere gevonden bronfragmenten. Kijk ook naar signalen zoals groeiplannen, vacatures, handmatige processen, complexe dienstverlening, afhankelijkheid van kenniswerk, regionale concurrentiedruk, compliance, vergunningstrajecten, klantcommunicatie, projectcoördinatie, administratieve belasting en digitale volwassenheid.

Doel:
Breng in kaart welke problemen of fricties waarschijnlijk spelen bij dit bedrijf en waarom die relevant zijn voor een verkoopgesprek of pilot met Smawa.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "uitdagingen": [
    {
      "titel": "",
      "omschrijving": "",
      "waarom_waarschijnlijk": "",
      "bron_of_signaal": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese",
      "impact": "laag | middel | hoog",
      "relevantie_voor_smawa": "",
      "mogelijke_gespreksvraag": ""
    }
  ],
  "samenvatting": ""
}

Richt je op maximaal 5 tot 8 sterke uitdagingen. Vermijd generieke claims zonder koppeling met {{Bedrijfsnaam}}.""",
    },
    {
        "prompt_id": "job_4_waardekansen",
        "title": "Job 4: Waardekansen",
        "description": "Concrete kansen voor pilot of verkoopgesprek.",
        "sort_order": 4,
        "is_system_prompt": False,
        "prompt_text": """Bepaal concrete waardekansen voor {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}} die Smawa kan vertalen naar een pilot, demo of verkoopgesprek.

Gebruik de bedrijfswebsite-content, diensten, documenten, vacatures, contactinformatie, doelgroepinformatie en eventuele gevonden signalen over processen, klantvragen, kenniswerk, vergunningen, administratie, projectcoördinatie, leadgeneratie, documentverwerking, offertes, planning, rapportages of klantcommunicatie.

Doel:
Vertaal de gevonden bedrijfsinformatie naar praktische kansen waarbij automatisering, AI, data, agents, procesoptimalisatie of digitale ondersteuning waarde kan leveren.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "waardekansen": [
    {
      "kans": "",
      "probleem_dat_wordt_opgelost": "",
      "mogelijke_smawa_oplossing": "",
      "pilot_idee": "",
      "verwachte_waarde": "",
      "bewijs_of_signaal": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese",
      "prioriteit": "laag | middel | hoog",
      "eerste_gespreksopening": ""
    }
  ],
  "beste_pilotvoorstel": {
    "titel": "",
    "waarom_deze_pilot": "",
    "eerste_scope": "",
    "benodigde_input_van_bedrijf": ""
  }
}

Formuleer de kansen concreet en verkoopbaar. Denk niet alleen aan algemene AI, maar aan toepasbare businesscases voor dit specifieke bedrijf.""",
    },
    {
        "prompt_id": "job_5_concurrenten",
        "title": "Job 5: Concurrenten",
        "description": "Regionale of landelijke concurrenten.",
        "sort_order": 5,
        "is_system_prompt": False,
        "prompt_text": """Identificeer waarschijnlijke concurrenten van {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik eerst bedrijfswebsite-content en bronfragmenten van {{Bedrijfsnaam}} om te bepalen in welke markt, niche en dienstverlening het bedrijf actief is. Gebruik daarna LLM-verrijking om regionale en landelijke concurrenten te bedenken of te herkennen. Markeer duidelijk welke concurrenten uit bronnen komen en welke op basis van AI-verrijking zijn toegevoegd.

Doel:
Maak een praktisch concurrentiebeeld dat bruikbaar is voor positionering, salesvoorbereiding en het bepalen van onderscheidende Smawa-kansen.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "marktsegment": "",
  "concurrenten": [
    {
      "naam": "",
      "plaats_of_regio": "",
      "type": "regionaal | landelijk | niche | alternatief",
      "waarom_concurrent": "",
      "mogelijke_overlap_in_diensten": "",
      "bron_of_redenering": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese",
      "mogelijke_positionering_tegenover_deze_concurrent": ""
    }
  ],
  "concurrentieanalyse": "",
  "mogelijke_differentiatiekansen_voor_smawa": []
}

Vermijd verzonnen exacte feiten zoals omzet, aantallen medewerkers of klanten, tenzij ze expliciet in bronnen staan. Als concurrenten niet met zekerheid gevonden zijn, geef ze als waarschijnlijke concurrenten.""",
    },
    {
        "prompt_id": "job_6_personen_rollen",
        "title": "Job 6: Personen en rollen",
        "description": "Namen, beslisrollen en eventuele LinkedIn-verwijzingen.",
        "sort_order": 6,
        "is_system_prompt": False,
        "prompt_text": """Breng relevante personen, rollen en mogelijke beslissers in kaart bij {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik de bedrijfswebsite-content, over-ons-pagina’s, teaminformatie, vacatures, PDF’s, contactpagina’s, e-mailadressen, auteurs, contactpersonen en eventuele bronfragmenten. Vul rollen voorzichtig aan op basis van functietitels, context en aannemelijke beslisstructuur. Markeer aannames duidelijk.

Doel:
Bepaal wie waarschijnlijk relevant zijn voor een salesgesprek, pilotvoorstel of technische/verkennende intake met Smawa.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "personen": [
    {
      "naam": "",
      "functie_of_rol": "",
      "mogelijke_beslisrol": "eindbeslisser | beïnvloeder | gebruiker | technisch_contact | operationeel_contact | onbekend",
      "contactgegevens": {
        "email": "",
        "telefoon": "",
        "linkedin": ""
      },
      "waar_gevonden": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese",
      "relevantie_voor_smawa": "",
      "aanbevolen_benadering": ""
    }
  ],
  "rolanalyse": {
    "waarschijnlijke_eindbeslisser": "",
    "beste_eerste_contact": "",
    "mogelijke_gebruikersgroepen": [],
    "ontbrekende_informatie": []
  }
}

Gebruik alleen echte namen, e-mailadressen, telefoonnummers of LinkedIn-verwijzingen als ze in bronnen staan. Verzin geen persoonlijke contactgegevens. Als LinkedIn niet gevonden is, laat het veld leeg of zet 'niet gevonden'.""",
    },
    {
        "prompt_id": "job_7_social_links",
        "title": "Job 7: Social links",
        "description": "Relevante bedrijfsprofielen en social kanalen.",
        "sort_order": 7,
        "is_system_prompt": False,
        "prompt_text": """Zoek en structureer relevante social links en online bedrijfsprofielen voor {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik beschikbare bedrijfswebsite-content, footer-links, contactpagina’s, metadata, structured data, documenten en eventuele bronfragmenten. Denk aan LinkedIn, Facebook, Instagram, YouTube, X/Twitter, Google Business Profile, brancheplatformen, vacatureplatformen en relevante bedrijfsgidsen.

Doel:
Maak een overzicht van online kanalen die bruikbaar zijn voor bedrijfsanalyse, salesvoorbereiding, social proof, doelgroepbegrip en contactstrategie.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "social_links": [
    {
      "platform": "",
      "url": "",
      "type": "bedrijfspagina | persoon | vacatureprofiel | brancheprofiel | reviewprofiel | onbekend",
      "relevantie": "laag | middel | hoog",
      "waarom_relevant": "",
      "bron_of_signaal": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese"
    }
  ],
  "ontbrekende_kanalen": [],
  "advies_voor_sales": ""
}

Neem alleen URLs op als ze in bronnen gevonden zijn of duidelijk uit betrouwbare context blijken. Verzin geen social URLs. Als een kanaal waarschijnlijk bestaat maar niet is gevonden, zet het bij ontbrekende_kanalen.""",
    },
    {
        "prompt_id": "job_8_marktcontext",
        "title": "Job 8: Marktcontext",
        "description": "Analyse in gewone taal van de markt.",
        "sort_order": 8,
        "is_system_prompt": False,
        "prompt_text": """Maak een marktcontextanalyse voor {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik eerst de bedrijfswebsite-content om te bepalen in welke markt het bedrijf actief is, welke diensten het levert, voor welke klanten het werkt en welke processen of trends relevant zijn. Verrijk daarna met algemene marktkennis, maar markeer dat als AI-verrijking wanneer er geen directe bron voor is.

Doel:
Geef in gewone taal een helder beeld van de markt waarin {{Bedrijfsnaam}} opereert, inclusief trends, drukpunten, kansen en risico’s die relevant zijn voor Smawa.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "marktsegment": "",
  "doelgroepen": [],
  "marktcontext": "",
  "belangrijke_trends": [
    {
      "trend": "",
      "impact_op_bedrijf": "",
      "bron_of_redenering": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese"
    }
  ],
  "drukpunten_in_de_markt": [],
  "kansen_in_de_markt": [],
  "relevantie_voor_smawa": "",
  "mogelijke_haakjes_voor_salesgesprek": []
}

Schrijf de analyse begrijpelijk en concreet. Vermijd te brede managementtaal. Koppel trends steeds terug naar {{Bedrijfsnaam}}.""",
    },
    {
        "prompt_id": "job_9_technologie_indicaties",
        "title": "Job 9: Technologie-indicaties",
        "description": "Zichtbare en aannemelijke technologie/processen.",
        "sort_order": 9,
        "is_system_prompt": False,
        "prompt_text": """Analyseer zichtbare en aannemelijke technologie-indicaties bij {{Bedrijfsnaam}} uit {{Bedrijfsplaats}} in de regio {{Regio}}.

Gebruik bedrijfswebsite-content, metadata, formulieren, scripts, vacatureteksten, PDF’s, dienstbeschrijvingen, procesbeschrijvingen en andere bronfragmenten. Kijk naar gebruikte websiteplatformen, formulieren, CRM-signalen, marketingtools, documentprocessen, teken- of rekensoftware, projectmanagement, klantportalen, e-mailprocessen, datastromen en handmatige workflows. Markeer duidelijk wat zichtbaar is en wat alleen aannemelijk is.

Doel:
Bepaal welke technologie, platformen of procesmiddelen zichtbaar of waarschijnlijk worden gebruikt en waar Smawa kansen kan zien voor automatisering, AI-agents, koppelingen, data-extractie of procesverbetering.

Geef output in deze structuur:

{
  "bedrijf": "{{Bedrijfsnaam}}",
  "plaats": "{{Bedrijfsplaats}}",
  "regio": "{{Regio}}",
  "technologie_indicaties": [
    {
      "categorie": "website | marketing | crm | documenten | planning | projectmanagement | vaksoftware | communicatie | data | onbekend",
      "indicatie": "",
      "waarvoor_waarschijnlijk_gebruikt": "",
      "bron_of_signaal": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese",
      "zekerheid": "laag | middel | hoog",
      "mogelijke_smawa_kans": ""
    }
  ],
  "procesindicaties": [
    {
      "proces": "",
      "huidige_aanpak_waarschijnlijk": "",
      "automatiseringskans": "",
      "bewijsniveau": "bron | afgeleid | ai_hypothese"
    }
  ],
  "aanbevolen_technische_vervolgvragen": [],
  "beste_automatiseringshaakje": ""
}

Noem geen specifieke software als feit tenzij die zichtbaar in bronnen staat. Als software alleen logisch of branchegebruikelijk is, markeer dit als AI-hypothese.""",
    },
]


def seed_default_analysis_prompts(db: Session) -> None:
    changed = False
    for item in DEFAULT_ANALYSIS_PROMPTS:
        prompt = db.get(AnalysisPrompt, item["prompt_id"])
        if prompt:
            continue
        db.add(AnalysisPrompt(**item))
        changed = True
    if changed:
        db.commit()


class AnalysisService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai = AIService(db)
        self.settings = get_settings()

    def create_company_analysis(self, website_id: int) -> AnalysisRun:
        website = self.db.get(Website, website_id)
        if not website:
            raise ValueError("Website not found")
        seed_default_analysis_prompts(self.db)
        run = AnalysisRun(website_id=website_id, status="queued", model=f"{self.ai.agent_provider}:{self.ai.agent_model}")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    async def run_company_analysis(self, website_id: int) -> AnalysisRun:
        run = self.create_company_analysis(website_id)
        return await self.run_analysis(run.id)

    async def run_analysis(self, analysis_id: int) -> AnalysisRun:
        run = self.db.get(AnalysisRun, analysis_id)
        if not run:
            raise ValueError("Analysis not found")
        website = self.db.get(Website, run.website_id)
        if not website:
            raise ValueError("Website not found")
        seed_default_analysis_prompts(self.db)
        run.status = "running"
        run.started_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        try:
            context, sources = await self._build_context(run.website_id)
            variables = await self._run_job(run, "job_1_code_fields", {}, context, sources, include_general=False)
            extracted = self._normalize_variables(variables, website)
            run.extracted_variables = json.dumps(extracted, ensure_ascii=False)
            self.db.commit()
            prompt_ids = [
                "job_2_bedrijfsprofiel",
                "job_3_uitdagingen",
                "job_4_waardekansen",
                "job_5_concurrenten",
                "job_6_personen_rollen",
                "job_7_social_links",
                "job_8_marktcontext",
                "job_9_technologie_indicaties",
            ]
            for prompt_id in prompt_ids:
                await self._run_job(run, prompt_id, extracted, context, sources, include_general=True)
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(run)
            return run

    async def _run_job(
        self,
        run: AnalysisRun,
        prompt_id: str,
        variables: dict[str, str],
        context: str,
        sources: list[dict[str, Any]],
        include_general: bool,
    ) -> dict[str, Any]:
        prompt = self.db.get(AnalysisPrompt, prompt_id)
        if not prompt or not prompt.prompt_text.strip():
            raise ValueError(f"Analysis prompt missing: {prompt_id}")
        rendered = self._render_prompt(prompt.prompt_text, variables)
        if include_general:
            general = self.db.get(AnalysisPrompt, "general_instruction")
            if general:
                rendered = f"{self._render_prompt(general.prompt_text, variables)}\n\n==\n\n{rendered}"
        full_prompt = f"{rendered}\n\nBeschikbare broncontext:\n{context}"
        result = AnalysisJobResult(
            analysis_run_id=run.id,
            prompt_id=prompt_id,
            rendered_prompt=rendered,
            status="running",
            sources=json.dumps(sources, ensure_ascii=False),
        )
        self.db.add(result)
        self.db.commit()
        try:
            text = await self.ai.complete(full_prompt, max_tokens=1800)
            parsed = self._parse_json(text)
            result.result_text = text
            result.result_json = json.dumps(parsed, ensure_ascii=False) if parsed is not None else ""
            result.summary = self._summarize_result(parsed if parsed is not None else text)
            result.status = "completed"
            result.completed_at = datetime.utcnow()
            self.db.commit()
            await self._store_insight(run, prompt_id, result.summary or text[:700], sources)
            return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.completed_at = datetime.utcnow()
            self.db.commit()
            raise

    async def _store_insight(self, run: AnalysisRun, prompt_id: str, text: str, sources: list[dict[str, Any]]) -> None:
        embedding = await self.ai.embed(text)
        self.db.add(
            AnalysisInsight(
                analysis_run_id=run.id,
                website_id=run.website_id,
                prompt_id=prompt_id,
                title=prompt_id.replace("_", " ").title()[:255],
                text=text,
                evidence_level=self._find_evidence_level(text),
                sources=json.dumps(sources[:8], ensure_ascii=False),
                embedding_vector=self._pgvector(embedding),
                embedding=embedding_to_json(embedding),
                embedding_model=self.settings.default_embedding_model,
            )
        )
        self.db.commit()

    async def _build_context(self, website_id: int) -> tuple[str, list[dict[str, Any]]]:
        website = self.db.get(Website, website_id)
        if not website:
            raise ValueError("Website not found")
        documents = (
            self.db.query(Document)
            .filter(Document.website_id == website_id)
            .order_by(Document.created_at.desc())
            .limit(60)
            .all()
        )
        document_ids = [document.id for document in documents]
        chunks: list[tuple[ContentChunk, Document]] = []
        if document_ids:
            chunks = (
                self.db.query(ContentChunk, Document)
                .join(Document)
                .filter(ContentChunk.document_id.in_(document_ids))
                .order_by(ContentChunk.score_hint.desc())
                .limit(80)
                .all()
            )
        semantic_chunks = await self._semantic_context_chunks(
            website,
            "bedrijfsnaam bedrijfsplaats regio vestigingsplaats adres contact over ons organisatie profiel",
            document_ids,
            limit=24,
        )
        prioritized_documents = self._prioritize_documents(documents)
        sources = [
            {"document_id": doc.id, "title": doc.title, "url": doc.source_url, "summary": doc.summary}
            for doc in prioritized_documents[:20]
        ]
        parts = [
            "== Huidige bedrijfscontext ==",
            f"Website ID: {website.id}",
            f"Website URL: {website.url}",
            f"Bekende bedrijfsnaam uit websiteprofiel: {website.company_name or 'onbekend'}",
            "Gebruik deze website en alleen bijbehorende documenten als primaire context voor dit bedrijf.",
        ]
        for chunk, doc, score in semantic_chunks:
            parts.append(
                f"[Semantisch relevant fragment {chunk.id} uit document {doc.id}, score {score:.4f}] "
                f"{doc.title}\nURL: {doc.source_url}\nFragment: {chunk.text[:1100]}"
            )
        for doc in prioritized_documents:
            parts.append(f"[Document {doc.id}] {doc.title}\nURL: {doc.source_url}\nSamenvatting: {doc.summary}\nTekst: {doc.text_content[:1200]}")
        seen_semantic = {chunk.id for chunk, _, _ in semantic_chunks}
        for chunk, doc in chunks:
            if chunk.id in seen_semantic:
                continue
            parts.append(f"[Chunk {chunk.id} uit document {doc.id}] {doc.title}\nURL: {doc.source_url}\nFragment: {chunk.text[:900]}")
        return "\n\n---\n\n".join(parts)[:45000], sources

    async def _semantic_context_chunks(
        self,
        website: Website,
        query: str,
        document_ids: list[int],
        limit: int,
    ) -> list[tuple[ContentChunk, Document, float]]:
        if not document_ids:
            return []
        query_embedding = await self.ai.embed(f"{website.company_name} {website.url} {query}")
        scored = []
        rows = (
            self.db.query(ContentChunk, Document)
            .join(Document, ContentChunk.document_id == Document.id)
            .filter(ContentChunk.document_id.in_(document_ids))
            .all()
        )
        for chunk, document in rows:
            vector = embedding_from_json(chunk.embedding)
            vector_score = cosine(query_embedding, vector) if vector else 0.0
            text_score = self._company_context_score(document, chunk.text)
            scored.append((vector_score + text_score, chunk, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(chunk, document, score) for score, chunk, document in scored[:limit] if score > 0]

    def _prioritize_documents(self, documents: list[Document]) -> list[Document]:
        return sorted(
            documents,
            key=lambda document: self._company_context_score(document, document.text_content or document.summary),
            reverse=True,
        )

    def _company_context_score(self, document: Document, text: str) -> float:
        haystack = " ".join([document.title, document.source_url, document.file_name, document.summary, text[:3000]]).lower()
        score = 0.0
        keywords = [
            "contact",
            "adres",
            "vestiging",
            "plaats",
            "regio",
            "over ons",
            "organisatie",
            "bedrijf",
            "bedrijfsnaam",
            "kvk",
            "postcode",
            "telefoon",
        ]
        for keyword in keywords:
            if keyword in haystack:
                score += 0.15
        if re.search(r"\b[1-9][0-9]{3}\s?[a-z]{2}\b", haystack, flags=re.I):
            score += 0.4
        if re.search(r"\b(tel|telefoon|e-mail|email)\b", haystack, flags=re.I):
            score += 0.2
        if document.source_url.rstrip("/").count("/") <= 3:
            score += 0.25
        return score

    def _render_prompt(self, prompt_text: str, variables: dict[str, str]) -> str:
        rendered = prompt_text
        for key in ["Bedrijfsnaam", "Bedrijfsplaats", "Regio"]:
            rendered = rendered.replace(f"{{{{{key}}}}}", variables.get(key) or "onbekend")
        return rendered

    def _parse_json(self, text: str) -> Any:
        clean = text.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
        clean = re.sub(r"\s*```$", "", clean)
        for candidate in [clean, self._extract_json_object(clean)]:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _extract_json_object(self, text: str) -> str:
        start = text.find("{")
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(text[start:], start=start):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return ""

    def _normalize_variables(self, value: dict[str, Any], website: Website) -> dict[str, str]:
        company_name = self._clean_variable(value.get("Bedrijfsnaam"))
        company_place = self._clean_variable(value.get("Bedrijfsplaats"))
        region = self._clean_variable(value.get("Regio"))
        return {
            "Bedrijfsnaam": company_name or website.company_name or "onbekend",
            "Bedrijfsplaats": company_place or "onbekend",
            "Regio": region or "onbekend",
        }

    def _clean_variable(self, value: Any) -> str:
        cleaned = str(value or "").strip()
        if cleaned.lower() in {"", "onbekend", "unknown", "n/a", "niet gevonden", "null", "none"}:
            return ""
        return cleaned

    def _summarize_result(self, value: Any) -> str:
        if isinstance(value, dict):
            for key in ["samenvatting", "marktcontext", "concurrentieanalyse"]:
                if value.get(key):
                    return str(value[key])[:900]
            return json.dumps(value, ensure_ascii=False)[:900]
        return str(value)[:900]

    def _find_evidence_level(self, text: str) -> str:
        lowered = text.lower()
        for level in ["bron", "afgeleid", "ai_hypothese"]:
            if level in lowered:
                return level
        return ""

    def _pgvector(self, embedding: list[float]) -> list[float]:
        vector = embedding[:1536]
        if len(vector) < 1536:
            vector.extend([0.0] * (1536 - len(vector)))
        return vector


def serialize_analysis_run(run: AnalysisRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "website_id": run.website_id,
        "status": run.status,
        "model": run.model,
        "extracted_variables": _json_loads(run.extracted_variables, {}),
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "jobs": [
            {
                "id": job.id,
                "prompt_id": job.prompt_id,
                "status": job.status,
                "summary": job.summary,
                "result_text": job.result_text,
                "result_json": _json_loads(job.result_json, None),
                "sources": _json_loads(job.sources, []),
                "error": job.error,
                "completed_at": job.completed_at,
            }
            for job in sorted(run.job_results, key=lambda item: item.prompt.sort_order if item.prompt else item.id)
        ],
    }


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback
