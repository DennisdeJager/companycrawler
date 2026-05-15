# MCP

## Doel en context

Companycrawler gebruikt MCP om dezelfde crawl-, zoek- en analysefunctionaliteit beschikbaar te maken voor LLM-clients als de webconsole en REST API gebruiken.

De data komt uit publiek toegankelijke websites die als website-record zijn aangemaakt. Een scan crawlt same-domain pagina's en bestanden, extraheert tekst, maakt samenvattingen en embeddings, en bewaart dode links of andere crawlproblemen als scanmelding. De agentische analyse gebruikt daarna bedrijfsmetadata, documentensamenvattingen en semantische chunks om een bruikbaar bedrijfsbeeld op te bouwen voor salesvoorbereiding, marktverkenning en PoC-briefings.

Belangrijke interpretatieregel: MCP-output is analysecontext, geen definitieve waarheid. Bij klantcommunicatie moeten claims worden gecontroleerd tegen de meegegeven bron-URL's.

## Transport

- Manifest: `GET /mcp`
- JSON-RPC endpoint: `POST /mcp`
- Directe toolroutes: `POST /mcp/tools/<tool_name>`
- Protocolversie: `2025-06-18`

## Websiteprofiel datacontract

Website-records bevatten `url`, `company_name`, `company_place`, `region` en `logo_url`.
De API-route `/api/detect-company-name` probeert deze velden uit de homepage af te leiden, zodat latere MCP-tools dezelfde bedrijfsnaam-, plaats- en regioregels kunnen gebruiken als de UI.

## Tools

### list_websites

- Doel: toont beschikbare website-records met hun profielmetadata, zodat een client een `website_id` kan kiezen.
- Inputschema: `{}`
- Outputschema: `{ "websites": [{ "id": number, "url": string, "company_name": string, "company_place": string, "region": string, "logo_url": string }] }`
- Autorisatie: huidige applicatiecontext; later server-side rechten per gebruiker/rol.
- Foutgedrag: operationele fouten komen als standaard MCP JSON-RPC error terug.

### start_scan

- Doel: zet een publieke same-domain crawl in de wachtrij voor een bestaand website-record.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "id": number, "status": string, "progress": number, "message": string, "error": string }`
- Autorisatie: beheer-/scanrechten zodra autorisatie op MCP wordt afgedwongen.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat. Dode links verschijnen later in `error` van de scanstatus.

### get_scan_status

- Doel: leest voortgang, status, workerbericht en eventuele crawlproblemen zoals dode links of fatale fouten.
- Inputschema: `{ "scan_id": number }`
- Outputschema: `{ "id": number, "status": string, "progress": number, "message": string, "error": string }`
- Autorisatie: toegang tot de betreffende website/scan.
- Foutgedrag: `{ "error": "Scan not found" }` wanneer de scan niet bestaat.

### search_company_data

- Doel: semantisch zoeken in gecrawlde documenten en chunks voor compacte, brongekoppelde LLM-context.
- Inputschema: `{ "query": string, "website_id"?: number | null, "limit"?: number }`
- Outputschema: `{ "results": [{ "document_id": number, "website_id": number, "company_name": string, "source_url": string, "title": string, "summary": string, "content_type": string, "score": number }] }`
- Autorisatie: toegang tot de gevonden websitecontent.
- Foutgedrag: validatiefouten op lege query of ongeldige limiet; operationele fouten als standaard MCP error.

### get_company_profile

- Doel: geeft een brede contextsnapshot van een bedrijf terug, inclusief websiteprofiel en documentensamenvattingen.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "id": number, "url": string, "company_name": string, "logo_url": string, "documents": [{ "id": number, "title": string, "url": string, "summary": string }] }`
- Autorisatie: toegang tot de betreffende website.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat.

### list_analysis_prompts

- Doel: toont de beheerbare promptketen waarmee de agentische analyse werkt.
- Inputschema: `{}`
- Outputschema: `{ "prompts": [{ "prompt_id": string, "title": string, "description": string, "sort_order": number, "is_system_prompt": boolean, "updated_at": datetime }] }`
- Autorisatie: lezen voor gebruikers met analysetoegang; wijzigen blijft via REST/UI beheer.
- Foutgedrag: operationele fouten als standaard MCP error.

### run_company_analysis

- Doel: draait de bedrijfsanalyseketen voor een website op basis van profielmetadata, samenvattingen en semantische context.
- Inputschema: `{ "website_id": number }`
- Outputschema: `AnalysisRunRead` met `id`, `website_id`, `status`, `model`, `extracted_variables`, `error`, timestamps en `jobs`.
- Autorisatie: analysetoegang tot de website.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat; providerfouten worden in run/job `error` vastgelegd.

### get_company_analysis

- Doel: haalt een opgeslagen analyse-run op zonder opnieuw AI-kosten of wachttijd te veroorzaken.
- Inputschema: `{ "analysis_id": number }`
- Outputschema: `AnalysisRunRead`
- Autorisatie: toegang tot de analyse en onderliggende website.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer de analyse niet bestaat.

### generate_company_scenarios

- Doel: maakt scenario-klare kansen uit de laatste opgeslagen bedrijfsanalyse.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "website_id": number, "analysis_id": number, "scenarios": [{ "title": string, "input": string, "source_prompt": string }] }`
- Autorisatie: analysetoegang tot de website.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer er nog geen analyse beschikbaar is.

### generate_poc_brief

- Doel: maakt een compacte PoC-briefing met profiel, uitdagingen, waardekansen en technische haakjes.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "website_id": number, "analysis_id": number, "brief": { "bedrijf": string, "plaats": string, "regio": string, "profiel": string, "uitdagingen": string, "waardekansen": string, "technische_haakjes": string } }`
- Autorisatie: analysetoegang tot de website.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer er nog geen analyse beschikbaar is.

## Toekomstige tool: reset_website_data

- Doel: verwijdert alle scan- en analysedata van een bestaande website, terwijl het website-record en de beheerinstellingen blijven bestaan.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "status": "reset" }`
- Autorisatie: alleen gebruikers met beheerrechten.
- Foutgedrag: `404` wanneer de website niet bestaat; operationele fouten worden als standaard API/MCP-fout teruggegeven.
