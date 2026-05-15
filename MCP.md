# MCP

## Websiteprofiel datacontract

Website-records bevatten `url`, `company_name`, `company_place`, `region` en `logo_url`.
De API-route `/api/detect-company-name` probeert deze velden uit de homepage af te leiden, zodat latere MCP-tools dezelfde bedrijfsnaam-, plaats- en regioregels kunnen gebruiken als de UI.

## Toekomstige tool: reset_website_data

- Doel: verwijdert alle scan- en analysedata van een bestaande website, terwijl het website-record en de beheerinstellingen blijven bestaan.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "status": "reset" }`
- Autorisatie: alleen gebruikers met beheerrechten.
- Foutgedrag: `404` wanneer de website niet bestaat; operationele fouten worden als standaard API/MCP-fout teruggegeven.
