# companycrawler

Companycrawler verzamelt publieke bedrijfsinformatie vanaf de website van een bedrijf en bouwt daar een doorzoekbaar marketingprofiel van op. De app crawlt pagina's en bestanden binnen hetzelfde domein, maakt AI-samenvattingen en embeddings, en ontsluit de data via REST, Swagger, MCP en een webconsole.

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL, pgvector
- Worker: Python crawler met same-domain limieten
- Frontend: React + Vite
- Auth: Google OAuth token verificatie met first-user-admin flow
- AI providers: OpenAI en OpenRouter voor LLM taken; OpenAI-compatible embeddings met lokale fallback voor development

## Snel starten

```bash
cp .env.example .env
docker compose up --build
```

Daarna:

- Webconsole: http://localhost:8080
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- MCP manifest: http://localhost:8000/mcp

## Belangrijke scope

Deze tool verzamelt publieke websitecontent voor marketingdoeleinden. V1 voert geen security scanning, pentesting, kwetsbaarheidsdetectie, authenticatie-bypass, formulieraanvallen of poortscans uit.

## Crawler defaults

- Same-domain crawling
- Max 500 items per scan
- Max 25 MB per bestand
- Max depth 8
- Robots-aware waar mogelijk

