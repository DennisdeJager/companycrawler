# Deployment

## Lokaal/dev container

```bash
cp .env.example .env
docker compose up --build -d
```

Services:

- `api`: FastAPI op poort `8000`
- `worker`: achtergrondverwerker voor scans
- `frontend`: nginx met React build op poort `8080`
- `db`: PostgreSQL met pgvector

## Caddy mapping

Voor dev/public mapping:

```caddyfile
companycrawler.smawa.nl {
  reverse_proxy 127.0.0.1:8080
}
```

Wanneer API en frontend op hetzelfde domein draaien, proxyt nginx `/api` en `/mcp` door naar de backend.

## GitHub

Repository: `https://github.com/DennisdeJager/companycrawler`

Na elke code change:

1. Build/lint/test uitvoeren.
2. Commit en push naar GitHub.
3. Dev container opnieuw deployen.
4. Caddy reloaden indien mapping is gewijzigd.

