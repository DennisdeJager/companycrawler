# AI Context

Companycrawler gebruikt AI voor drie taken:

1. Bedrijfsnaam detecteren vanaf de homepage.
2. Korte samenvattingen maken per pagina of bestand.
3. Embeddings maken voor semantisch zoeken.

## Providers

De applicatie ondersteunt OpenAI en OpenRouter als LLM-providers. Modelcatalogi worden via de backend opgehaald en opgeslagen. Beheerders kiezen in de webconsole welk model gebruikt wordt voor scan/crawl taken.

Embeddings gebruiken standaard een OpenAI embedding model wanneer `OPENAI_API_KEY` beschikbaar is. In development valt de app terug op deterministische lokale embeddings zodat tests en UI zonder sleutel werken.

## Secrets

API keys staan alleen in `.env` of deployment environment variables. Keys worden nooit gecommit.

