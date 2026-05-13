# companycrawler

Companycrawler verzamelt publieke bedrijfsinformatie vanaf de website van een bedrijf en bouwt daar een doorzoekbaar marketingprofiel van op. De app crawlt pagina's en bestanden binnen hetzelfde domein, maakt AI-samenvattingen en embeddings, en ontsluit de data via REST, Swagger, MCP en een webconsole.

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL, pgvector
- Worker: Python crawler met same-domain limieten
- Frontend: React + Vite
- Auth: Google OAuth token verificatie met first-user-admin flow
- AI providers: OpenAI en OpenRouter voor LLM taken; centrale selectie voor summary-, embedding- en agentmodellen; OpenAI-compatible embeddings met lokale fallback voor development

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
- MCP JSON-RPC endpoint voor ChatGPT en andere MCP-clients: `POST http://localhost:8000/mcp`

## MCP gebruik

De MCP server ondersteunt Streamable HTTP via JSON-RPC op `/mcp`. Gebruik eerst `initialize`, daarna `tools/list` en vervolgens `tools/call`.

Voorbeeld:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

De oudere tool-endpoints onder `/mcp/tools/...` blijven beschikbaar voor bestaande scripts.

## Belangrijke scope

De eerste gebruiker die via Google inlogt wordt automatisch `admin`. Latere nieuwe Google gebruikers starten als `guest` en zien alleen de wacht-op-goedkeuring melding totdat een admin een rol toekent.

Deze tool verzamelt publieke websitecontent voor marketingdoeleinden. V1 voert geen security scanning, pentesting, kwetsbaarheidsdetectie, authenticatie-bypass, formulieraanvallen of poortscans uit.

## Crawler defaults

- Same-domain crawling
- Max 500 items per scan
- Max 25 MB per bestand
- Max depth 8
- Robots-aware waar mogelijk
