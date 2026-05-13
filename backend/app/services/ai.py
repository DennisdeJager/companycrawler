import hashlib
import json
import math
import re
from collections import Counter

import httpx

from app.core.config import get_settings


class AIService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def detect_company_name(self, url: str, homepage_text: str) -> str:
        title_match = re.search(r"<title>(.*?)</title>", homepage_text, re.I | re.S)
        seed = title_match.group(1) if title_match else homepage_text[:200]
        clean = re.sub(r"\s+", " ", seed).strip()
        if self.settings.openai_api_key:
            prompt = f"Extract only the full company name from this homepage text for {url}. Return only the name.\n\n{clean[:4000]}"
            result = await self._chat_openai(prompt, max_tokens=80)
            if result:
                return result.strip().strip('"')
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        return host.split(".")[0].replace("-", " ").title()

    async def summarize(self, title: str, text: str) -> tuple[str, str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if self.settings.openai_api_key:
            prompt = (
                "Vat deze pagina of dit bestand in maximaal 2 korte regels samen. "
                "Vertel bondig waar de content over gaat. Geef daarna op een nieuwe regel "
                "een ultrakorte 1-regel tree summary voorafgegaan door TREE:.\n\n"
                f"Titel: {title}\nContent: {clean[:6000]}"
            )
            result = await self._chat_openai(prompt, max_tokens=180)
            if result:
                lines = [line.strip() for line in result.splitlines() if line.strip()]
                tree = next((line[5:].strip() for line in lines if line.lower().startswith("tree:")), "")
                summary = " ".join(line for line in lines if not line.lower().startswith("tree:"))[:500]
                return summary or clean[:220], tree or (summary[:180] if summary else clean[:180])
        fallback = clean[:260] if clean else f"Content over {title or 'deze bron'}."
        return fallback, fallback[:180]

    async def embed(self, text: str) -> list[float]:
        if self.settings.openai_api_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                        json={"model": self.settings.default_embedding_model, "input": text[:8000]},
                    )
                    response.raise_for_status()
                    return response.json()["data"][0]["embedding"]
            except Exception:
                pass
        return self._local_embedding(text)

    async def list_models(self) -> list[dict[str, str]]:
        models: list[dict[str, str]] = []
        if self.settings.openai_api_key:
            models.extend(await self._list_openai_models())
        if self.settings.openrouter_api_key:
            models.extend(await self._list_openrouter_models())
        if not models:
            models = [
                {"provider": "openai", "model": self.settings.default_summary_model, "purpose": "summary", "best_for": "Goede balans tussen kwaliteit en kosten voor samenvattingen."},
                {"provider": "openai", "model": self.settings.default_embedding_model, "purpose": "embedding", "best_for": "Standaard embeddings voor semantische zoekopdrachten."},
                {"provider": "openrouter", "model": "openrouter/auto", "purpose": "summary", "best_for": "Fallback-routering wanneer OpenRouter is geconfigureerd."},
            ]
        return models

    async def _chat_openai(self, prompt: str, max_tokens: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    json={
                        "model": self.settings.default_summary_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""

    async def _list_openai_models(self) -> list[dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {self.settings.openai_api_key}"})
                response.raise_for_status()
                return [
                    {"provider": "openai", "model": item["id"], "purpose": "summary", "best_for": "Beschikbaar OpenAI model voor extractie en samenvattingen."}
                    for item in response.json().get("data", [])[:100]
                ]
        except Exception:
            return []

    async def _list_openrouter_models(self) -> list[dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"})
                response.raise_for_status()
                return [
                    {"provider": "openrouter", "model": item["id"], "purpose": "summary", "best_for": item.get("description", "OpenRouter model voor samenvattingen.")[:500]}
                    for item in response.json().get("data", [])[:100]
                ]
        except Exception:
            return []

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


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector)


def embedding_from_json(value: str) -> list[float]:
    try:
        return [float(item) for item in json.loads(value)]
    except Exception:
        return []
