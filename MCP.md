# MCP

## Toekomstige tool: reset_website_data

- Doel: verwijdert alle scan- en analysedata van een bestaande website, terwijl het website-record en de beheerinstellingen blijven bestaan.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "status": "reset" }`
- Autorisatie: alleen gebruikers met beheerrechten.
- Foutgedrag: `404` wanneer de website niet bestaat; operationele fouten worden als standaard API/MCP-fout teruggegeven.

