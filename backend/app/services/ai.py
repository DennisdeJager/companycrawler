import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.settings_store import get_setting


class AIProviderError(RuntimeError):
    pass


class AIService:
    def __init__(self, db: Session | None = None) -> None:
        self.settings = get_settings()
        self.db = db
        self.last_provider_error = ""

    @property
    def openai_api_key(self) -> str:
        return get_setting(self.db, "openai_api_key", self.settings.openai_api_key)

    @property
    def openrouter_api_key(self) -> str:
        return get_setting(self.db, "openrouter_api_key", self.settings.openrouter_api_key)

    @property
    def summary_model(self) -> str:
        return get_setting(self.db, "default_summary_model", self.settings.default_summary_model)

    @property
    def summary_provider(self) -> str:
        return get_setting(self.db, "default_summary_provider", self.settings.default_summary_provider)

    @property
    def embedding_model(self) -> str:
        return get_setting(self.db, "default_embedding_model", self.settings.default_embedding_model)

    @property
    def agent_provider(self) -> str:
        return get_setting(self.db, "default_agent_provider", self.settings.default_agent_provider)

    @property
    def agent_model(self) -> str:
        return get_setting(self.db, "default_agent_model", self.settings.default_agent_model)

    async def detect_company_name(self, url: str, homepage_text: str) -> str:
        return (await self.detect_company_profile(url, homepage_text))["company_name"]

    async def detect_company_profile(self, url: str, homepage_text: str) -> dict[str, str]:
        title_match = re.search(r"<title>(.*?)</title>", homepage_text, re.I | re.S)
        seed = title_match.group(1) if title_match else homepage_text[:200]
        clean = re.sub(r"\s+", " ", seed).strip()
        if self.openai_api_key:
            prompt = (
                "Bepaal uit deze homepage de bedrijfsnaam, vestigingsplaats en regio/provincie. "
                "Geef alleen JSON terug met keys company_name, company_place en region. "
                "Gebruik lege strings wanneer iets niet betrouwbaar te bepalen is.\n\n"
                f"URL: {url}\nHomepage tekst:\n{clean[:5000]}"
            )
            result = await self._chat_provider("openai", self.summary_model, prompt, max_tokens=180)
            parsed = self._parse_company_profile(result)
            if parsed["company_name"]:
                return parsed
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        return {"company_name": host.split(".")[0].replace("-", " ").title(), "company_place": "", "region": ""}

    async def test_provider(self, provider: str) -> dict[str, str | bool]:
        provider = (provider or "").lower()
        if provider not in {"openai", "openrouter"}:
            return {"ok": False, "provider": provider, "message": "Onbekende provider."}
        if not self._provider_has_key(provider):
            return {"ok": False, "provider": provider, "message": f"{provider} API key is niet ingesteld."}
        model = self.summary_model if provider == "openai" else (self.agent_model if self.agent_provider == "openrouter" else "openrouter/auto")
        result = await self._chat_provider(provider, model, "Antwoord alleen met: ok", max_tokens=12)
        if result:
            return {"ok": True, "provider": provider, "message": f"{provider} verbinding werkt met model {model}."}
        return {"ok": False, "provider": provider, "message": self.last_provider_error or f"{provider} gaf geen bruikbare respons."}

    async def summarize(self, title: str, text: str) -> tuple[str, str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if self._provider_has_key(self.summary_provider):
            prompt = (
                "Vat deze pagina of dit bestand in maximaal 2 korte regels samen. "
                "Vertel bondig waar de content over gaat. Geef daarna op een nieuwe regel "
                "een ultrakorte 1-regel tree summary voorafgegaan door TREE:.\n\n"
                f"Titel: {title}\nContent: {clean[:6000]}"
            )
            result = await self._chat_provider(self.summary_provider, self.summary_model, prompt, max_tokens=180)
            if result:
                lines = [line.strip() for line in result.splitlines() if line.strip()]
                tree = next((line[5:].strip() for line in lines if line.lower().startswith("tree:")), "")
                summary = " ".join(line for line in lines if not line.lower().startswith("tree:"))[:500]
                return summary or clean[:220], tree or (summary[:180] if summary else clean[:180])
        fallback = clean[:260] if clean else f"Content over {title or 'deze bron'}."
        return fallback, fallback[:180]

    async def complete(self, prompt: str, max_tokens: int = 1400) -> str:
        if self._provider_has_key(self.agent_provider):
            result = await self._chat_provider(self.agent_provider, self.agent_model, prompt, max_tokens=max_tokens)
            if result:
                return result
            raise AIProviderError(self.last_provider_error or f"{self.agent_provider} gaf geen bruikbare respons.")
        return self._fallback_completion(prompt)

    async def embed(self, text: str) -> list[float]:
        if self.openai_api_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {self.openai_api_key}"},
                        json={"model": self.embedding_model, "input": text[:8000]},
                    )
                    response.raise_for_status()
                    return response.json()["data"][0]["embedding"]
            except Exception:
                pass
        return self._local_embedding(text)

    async def list_models(self) -> list[dict[str, str]]:
        models: list[dict[str, str]] = []
        if self.openai_api_key:
            models.extend(await self._list_openai_models())
        if self.openrouter_api_key:
            models.extend(await self._list_openrouter_models())
        if not models:
            models = [
                self._model_info("openai", self.summary_model, "chat"),
                self._model_info("openai", self.embedding_model, "embedding"),
                self._model_info("openrouter", "openrouter/auto", "chat"),
            ]
        recommended = await self.recommend_agent_model(models)
        recommended_embedding = await self.recommend_embedding_model(models)
        for model in models:
            model["is_default"] = (
                (model["provider"] == recommended["provider"] and model["model"] == recommended["model"])
                or (model["provider"] == recommended_embedding["provider"] and model["model"] == recommended_embedding["model"])
            )
        return models

    async def recommend_agent_model(self, models: list[dict[str, str]]) -> dict[str, str]:
        candidates = [model for model in models if model.get("purpose") != "embedding"]
        if not candidates:
            return {"provider": self.agent_provider, "model": self.agent_model}
        if not self._provider_has_key(self.summary_provider):
            return self._local_agent_recommendation(candidates)

        catalog = "\n".join(
            f"- {item['provider']} | {item['model']} | {item.get('purpose', 'chat')} | {item.get('best_for', '')[:220]}"
            for item in candidates[:80]
        )
        prompt = (
            "Kies uit deze modelcatalogus precies een aanbevolen LLM voor agentische analyses van bedrijfsdomeinen. "
            "We analyseren publieke websitecontent, bedrijfsprofielen, uitdagingen, concurrenten, personen, social links, marktcontext en technologie-indicaties. "
            "Balans: hoge Nederlandse analysek kwaliteit, betrouwbare JSON-output, goede redeneercapaciteit en redelijke kosten. "
            "Geef alleen JSON terug met keys provider, model en reden.\n\n"
            f"Catalogus:\n{catalog}"
        )
        text = await self._chat_provider(self.summary_provider, self.summary_model, prompt, max_tokens=300)
        try:
            parsed = json.loads(re.search(r"\{.*\}", text, flags=re.S).group(0) if text else "{}")
            provider = str(parsed.get("provider", "")).strip()
            model = str(parsed.get("model", "")).strip()
            if any(item["provider"] == provider and item["model"] == model for item in candidates):
                return {"provider": provider, "model": model}
        except Exception:
            pass
        return self._local_agent_recommendation(candidates)

    async def recommend_embedding_model(self, models: list[dict[str, str]]) -> dict[str, str]:
        candidates = [model for model in models if model.get("purpose") == "embedding"]
        if not candidates:
            return {"provider": "openai", "model": self.embedding_model}
        if not self._provider_has_key(self.summary_provider):
            return self._local_embedding_recommendation(candidates)

        catalog = "\n".join(
            f"- {item['provider']} | {item['model']} | {item.get('best_for', '')[:220]}"
            for item in candidates[:60]
        )
        prompt = (
            "Kies uit deze embedding-modelcatalogus precies een aanbevolen model voor vectoropslag en semantisch zoeken "
            "op gecrawlde bedrijfswebsites. Balans: kwaliteit voor Nederlandse tekst, retrieval, kosten en brede beschikbaarheid. "
            "Geef alleen JSON terug met keys provider, model en reden.\n\n"
            f"Catalogus:\n{catalog}"
        )
        text = await self._chat_provider(self.summary_provider, self.summary_model, prompt, max_tokens=260)
        try:
            parsed = json.loads(re.search(r"\{.*\}", text, flags=re.S).group(0) if text else "{}")
            provider = str(parsed.get("provider", "")).strip()
            model = str(parsed.get("model", "")).strip()
            if any(item["provider"] == provider and item["model"] == model for item in candidates):
                return {"provider": provider, "model": model}
        except Exception:
            pass
        return self._local_embedding_recommendation(candidates)

    async def _chat_provider(self, provider: str, model: str, prompt: str, max_tokens: int) -> str:
        provider = (provider or "openai").lower()
        if provider == "openrouter":
            return await self._chat_openrouter(model, prompt, max_tokens)
        return await self._chat_openai(model, prompt, max_tokens)

    async def _chat_openai(self, model: str, prompt: str, max_tokens: int) -> str:
        self.last_provider_error = ""
        response_text = await self._responses_openai(model, prompt, max_tokens)
        if response_text:
            return response_text
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": max_tokens,
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json=payload,
                )
                if response.status_code == 400 and "max_completion_tokens" in response.text and "Unsupported parameter" in response.text:
                    fallback_payload = dict(payload)
                    fallback_payload["max_tokens"] = fallback_payload.pop("max_completion_tokens")
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.openai_api_key}"},
                        json=fallback_payload,
                    )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as exc:
            self.last_provider_error = self._provider_error("OpenAI chat completions", exc.response)
        except Exception:
            self.last_provider_error = "OpenAI chat completions gaf geen bruikbare respons."
        return ""

    async def _responses_openai(self, model: str, prompt: str, max_tokens: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={
                        "model": model,
                        "input": prompt,
                        "max_output_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                return self._extract_responses_text(response.json())
        except httpx.HTTPStatusError as exc:
            self.last_provider_error = self._provider_error("OpenAI responses", exc.response)
        except Exception:
            self.last_provider_error = "OpenAI responses gaf geen bruikbare respons."
        return ""

    async def _chat_openrouter(self, model: str, prompt: str, max_tokens: int) -> str:
        self.last_provider_error = ""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_api_key}",
                        "HTTP-Referer": self.settings.app_url,
                        "X-Title": self.settings.app_name,
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as exc:
            self.last_provider_error = self._provider_error("OpenRouter chat completions", exc.response)
        except Exception:
            self.last_provider_error = "OpenRouter chat completions gaf geen bruikbare respons."
        return ""

    async def _list_openai_models(self) -> list[dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {self.openai_api_key}"})
                response.raise_for_status()
                return [
                    self._model_info("openai", item["id"], self._classify_model(item["id"]))
                    for item in response.json().get("data", [])[:100]
                ]
        except Exception:
            return []

    async def _list_openrouter_models(self) -> list[dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {self.openrouter_api_key}"})
                response.raise_for_status()
                return [
                    self._model_info(
                        "openrouter",
                        item["id"],
                        self._classify_model(item["id"], str(item.get("architecture", {}).get("modality", ""))),
                        item.get("description", ""),
                    )
                    for item in response.json().get("data", [])[:100]
                ]
        except Exception:
            return []

    def _provider_has_key(self, provider: str) -> bool:
        provider = (provider or "openai").lower()
        if provider == "openrouter":
            return bool(self.openrouter_api_key)
        return bool(self.openai_api_key)

    def _classify_model(self, model: str, modality: str = "") -> str:
        name = f"{model} {modality}".lower()
        if "embed" in name:
            return "embedding"
        if any(token in name for token in ["image", "vision", "omni", "audio", "tts", "whisper"]):
            return "multimodal"
        if any(token in name for token in ["reason", "o1", "o3", "o4", "gpt-5"]):
            return "reasoning"
        return "chat"

    def _model_info(self, provider: str, model: str, purpose: str, description: str = "") -> dict[str, str]:
        strengths = {
            "embedding": "Goed voor vectoropslag en semantisch zoeken; niet geschikt voor tekstgeneratie of agent-analyses.",
            "reasoning": "Goed voor diepere analyse, structuur, JSON-output en complexe afwegingen; meestal duurder en trager dan lichte chatmodellen.",
            "multimodal": "Goed wanneer beeld, audio of gemengde input nodig is; vaak overkill voor pure tekstanalyses.",
            "chat": "Goed voor samenvattingen, extractie en algemene teksttaken; minder sterk dan reasoning-modellen bij complexe agentstappen.",
        }
        text = description.strip() or strengths.get(purpose, strengths["chat"])
        if "Goed voor" not in text and "Niet goed" not in text:
            text = f"{text[:360]} Goed/niet goed: {strengths.get(purpose, strengths['chat'])}"
        return {"provider": provider, "model": model, "purpose": purpose, "best_for": text[:512]}

    def _local_agent_recommendation(self, models: list[dict[str, str]]) -> dict[str, str]:
        configured = next((item for item in models if item["provider"] == self.agent_provider and item["model"] == self.agent_model), None)
        if configured:
            return configured
        for preferred in ["gpt-5.4-mini", "gpt-5.4", "gpt-4.1", "openrouter/auto"]:
            match = next((item for item in models if item["model"] == preferred), None)
            if match:
                return match
        non_embedding = next((item for item in models if item.get("purpose") != "embedding"), models[0])
        return non_embedding

    def _local_embedding_recommendation(self, models: list[dict[str, str]]) -> dict[str, str]:
        configured = next((item for item in models if item["provider"] == "openai" and item["model"] == self.embedding_model), None)
        if configured:
            return configured
        for preferred in ["text-embedding-3-small", "text-embedding-3-large"]:
            match = next((item for item in models if item["model"] == preferred), None)
            if match:
                return match
        return models[0]

    def _local_embedding(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        counts = Counter(tokens)
        vector = [0.0] * 1536
        for token, count in counts.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = digest[0] % len(vector)
            vector[index] += float(count)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]

    def _extract_responses_text(self, payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        parts: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()

    def _parse_company_profile(self, value: str) -> dict[str, str]:
        try:
            match = re.search(r"\{.*\}", value or "", flags=re.S)
            payload = json.loads(match.group(0) if match else value)
            return {
                "company_name": str(payload.get("company_name") or payload.get("Bedrijfsnaam") or "").strip().strip('"'),
                "company_place": str(payload.get("company_place") or payload.get("Bedrijfsplaats") or payload.get("plaats") or "").strip().strip('"'),
                "region": str(payload.get("region") or payload.get("Regio") or "").strip().strip('"'),
            }
        except Exception:
            return {"company_name": (value or "").strip().strip('"'), "company_place": "", "region": ""}

    def _provider_error(self, endpoint: str, response: httpx.Response) -> str:
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("code") or "")
        except Exception:
            detail = response.text[:220]
        detail = re.sub(r"sk-[A-Za-z0-9_\-]+", "[redacted]", detail or "")
        suffix = f": {detail[:260]}" if detail else ""
        return f"{endpoint} faalde met HTTP {response.status_code}{suffix}"

    def _fallback_completion(self, prompt: str) -> str:
        if "Wat is de naam, de woonplaats en regio van dit bedrijf" in prompt:
            return json.dumps({"Bedrijfsnaam": "onbekend", "Bedrijfsplaats": "onbekend", "Regio": "onbekend"}, ensure_ascii=False)
        return json.dumps(
            {
                "samenvatting": "Lokale fallback: configureer een OpenAI of OpenRouter API key voor volledige AI-analyse.",
                "bewijsniveau": "ai_hypothese",
                "opmerking": "Deze output is deterministisch gegenereerd omdat er geen AI-provider beschikbaar is.",
            },
            ensure_ascii=False,
        )


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector)


def embedding_from_json(value: str) -> list[float]:
    try:
        return [float(item) for item in json.loads(value)]
    except Exception:
        return []
