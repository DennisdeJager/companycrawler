# Deployment

## Lokaal/dev container

```bash
cp .env.example .env
docker compose up --build -d
```

```codex-deploy
{
  "targets": {
    "dev": {
      "host": "192.168.10.12",
      "user": "root",
      "remotePath": "/opt/capps/apps/companycrawler",
      "composeFile": "docker-compose.yml",
      "services": ["db", "api", "worker", "web"],
      "postDeployWaitSeconds": 25,
      "healthUrls": ["http://192.168.10.12:8080/api/health"],
      "readyUrls": ["http://192.168.10.12:8080/mcp"],
      "postDeployChecks": []
    }
  }
}
```

Services:

- `api`: FastAPI op poort `8000`
- `worker`: achtergrondverwerker voor scans
- `web`: nginx met React build op poort `8080` of `WEB_PORT`
- `db`: PostgreSQL met pgvector

## Caddy mapping

Voor dev/public mapping:

```caddyfile
companycrawler.smawa.nl {
  reverse_proxy 127.0.0.1:8080
}
```

Wanneer API en frontend op hetzelfde domein draaien, proxyt nginx `/api` en `/mcp` door naar de backend.

## Security checks

- `GET /api/health` blijft publiek voor load balancers en ALM.
- Swagger/OpenAPI loopt via `/api/docs` en `/api/openapi.json` en vereist een admin-sessie.
- `GET /mcp` en `POST /mcp` moeten zonder Bearer API token `401` geven.
- MCP-readiness checks die het manifest willen lezen moeten een geldig API token meesturen.

## Google OAuth

De webconsole gebruikt een server-side Google OAuth redirect-flow. Hiervoor is een OAuth Client ID van het type `Web application` nodig.

Voor dev/public login:

- Authorized redirect URIs: `https://companycrawler.smawa.nl/api/auth/google/callback`
- Authorized domains: `smawa.nl`
- Authorized JavaScript origins: niet nodig
- `.env`: `GOOGLE_CLIENT_ID` en `GOOGLE_CLIENT_SECRET` moeten ingevuld zijn

De Settings pagina toont de actieve browser-origin, `APP_URL` origin en redirect URI uit `.env`, zodat zichtbaar is welke redirect URI in Google Cloud geregistreerd moet zijn.

## GitHub

Repository: `https://github.com/DennisdeJager/companycrawler`

Na elke code change:

1. Build/lint/test uitvoeren.
2. Commit en push naar GitHub.
3. Dev container opnieuw deployen.
4. Caddy reloaden indien mapping is gewijzigd.
