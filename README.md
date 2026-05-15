# companycrawler

Companycrawler verzamelt publieke bedrijfsinformatie vanaf de website van een bedrijf en bouwt daar een doorzoekbaar marketingprofiel van op. De app crawlt pagina's en bestanden binnen hetzelfde domein, maakt AI-samenvattingen en embeddings, en ontsluit de data via REST, Swagger, MCP en een webconsole.

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL, pgvector
- Worker: Python crawler met same-domain limieten
- Frontend: React + Vite
- Auth: Google OAuth token verificatie met first-user-admin flow
- API/MCP auth: websessies voor de console, hashed Bearer tokens met scopes voor externe clients
- AI providers: OpenAI en OpenRouter voor LLM taken; centrale selectie voor summary-, embedding- en agentmodellen; OpenAI-compatible embeddings met lokale fallback voor development

## Snel starten

```bash
cp .env.example .env
docker compose up --build
```

Daarna:

- Webconsole: http://localhost:8080
- API: http://localhost:8000
- Swagger: http://localhost:8000/api/docs, alleen voor admins met sessiecookie
- MCP manifest: http://localhost:8000/mcp, alleen met Bearer API token of OAuth access token
- MCP JSON-RPC endpoint voor ChatGPT en andere MCP-clients: `POST http://localhost:8000/mcp`

## MCP gebruik

De MCP server ondersteunt Streamable HTTP via JSON-RPC op `/mcp`. MCP accepteert alleen Bearer tokens via `Authorization: Bearer <token>`, geen browsercookie.

Voor server-to-server gebruik maak je tokens aan via Settings > API & MCP tokens. Voor OpenAI ChatGPT Developer Mode/custom apps ondersteunt de server OAuth discovery, dynamic client registration en authorization-code + PKCE via:

- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-authorization-server`
- `/oauth/register`
- `/oauth/authorize`
- `/oauth/token`

Scopes zijn `read`, `execute` en `admin`; `execute` is nodig voor tools die scans of analyses starten. OAuth voor MCP geeft maximaal `read execute` uit en vereist een ingelogde Companycrawler gebruiker met rol `user` of `admin`.

Voorbeeld:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

De oudere tool-endpoints onder `/mcp/tools/...` blijven beschikbaar voor bestaande scripts.

Alle niet-publieke REST-routes vereisen een geldige sessie. Beheeracties zoals gebruikers, provider secrets, promptbeheer, logs, tokenbeheer, reset/verwijderen en Swagger vereisen de rol `admin`.

Zet in elke gedeelde of publieke omgeving een sterke unieke `APP_SECRET_KEY`; deze sleutel ondertekent websessies. Gebruik nooit de developmentwaarde uit `.env.example` buiten lokale tests.

## Belangrijke scope

De eerste gebruiker die via Google inlogt wordt automatisch `admin`. Latere nieuwe Google gebruikers starten als `guest` en zien alleen de wacht-op-goedkeuring melding totdat een admin een rol toekent.

Deze tool verzamelt publieke websitecontent voor marketingdoeleinden. V1 voert geen security scanning, pentesting, kwetsbaarheidsdetectie, authenticatie-bypass, formulieraanvallen of poortscans uit.

## Crawler defaults

- Same-domain crawling
- Max 500 items per scan
- Max 25 MB per bestand
- Max depth 8
- Robots-aware waar mogelijk
