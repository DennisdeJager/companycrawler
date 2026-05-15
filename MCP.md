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
- Authenticatie: verplicht via `Authorization: Bearer <api-token>`. MCP accepteert bewust geen browsercookie.
- Scopes: `read` voor lezen/zoeken, `execute` voor scans of analyses starten, `admin` voor toekomstige beheer/destructieve tools.

Tokens worden aangemaakt in de webconsole via Settings > API & MCP tokens. De tokenwaarde wordt alleen direct na aanmaken getoond; server-side wordt alleen een SHA-256 hash bewaard. Ongeldige, ingetrokken of verlopen tokens krijgen `401`; tokens zonder juiste scope krijgen `403` of een MCP JSON-RPC error met scope-melding.

## Websiteprofiel datacontract

Website-records bevatten `url`, `company_name`, `company_place`, `region` en `logo_url`.
De API-route `/api/detect-company-name` probeert deze velden uit de homepage af te leiden, zodat latere MCP-tools dezelfde bedrijfsnaam-, plaats- en regioregels kunnen gebruiken als de UI.

## Tools

### list_websites

- Doel: toont beschikbare website-records met hun profielmetadata, zodat een client een `website_id` kan kiezen.
- Inputschema: `{}`
- Outputschema: `{ "websites": [{ "id": number, "url": string, "company_name": string, "company_place": string, "region": string, "logo_url": string }] }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: operationele fouten komen als standaard MCP JSON-RPC error terug.

### upsert_website

- Doel: maakt een nieuw website-record aan of werkt een bestaand record met dezelfde URL bij. Wanneer metadata ontbreekt kan de homepage worden gebruikt om bedrijfsnaam, plaats, regio en logo te detecteren.
- Inputschema: `{ "url": string, "company_name"?: string, "company_place"?: string, "region"?: string, "logo_url"?: string, "detect_profile"?: boolean }`
- Outputschema: `{ "created": boolean, "website": { "id": number, "url": string, "company_name": string, "company_place": string, "region": string, "logo_url": string, "created_at": datetime, "updated_at": datetime }, "profile_detection_error"?: string }`
- Autorisatie: API token met minimaal `execute`.
- Foutgedrag: ontbrekende of ongeldige URL geeft een MCP JSON-RPC error. Als profieldetectie faalt maar er voldoende fallbackmetadata is, wordt het record toch aangemaakt en staat de fout in `profile_detection_error`.

### start_scan

- Doel: zet een publieke same-domain crawl in de wachtrij voor een bestaand website-record.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "id": number, "website_id": number, "status": string, "progress": number, "message": string, "error": string, "auto_analyze": boolean, "analysis_run_id": number | null }`
- Autorisatie: API token met minimaal `execute`.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat. Dode links verschijnen later in `error` van de scanstatus.

### scan_and_analyze_website

- Doel: maakt of update een website-record, zet direct een scan in de wachtrij en markeert deze scan zodat de worker na succesvolle afronding automatisch de bedrijfsanalyse start.
- Inputschema: `{ "url": string, "company_name"?: string, "company_place"?: string, "region"?: string, "logo_url"?: string, "detect_profile"?: boolean }`
- Outputschema: `{ "website": object, "scan": { "id": number, "website_id": number, "status": string, "progress": number, "message": string, "auto_analyze": true, "analysis_run_id": number | null }, "analysis": null, "profile_detection_error"?: string }`
- Autorisatie: API token met minimaal `execute`.
- Foutgedrag: ontbrekende of ongeldige URL geeft een MCP JSON-RPC error. Profieldetectiefouten blokkeren de scan niet wanneer een veilige fallback beschikbaar is.

### get_scan_status

- Doel: leest voortgang, status, workerbericht en eventuele crawlproblemen zoals dode links of fatale fouten.
- Inputschema: `{ "scan_id": number }`
- Outputschema: `{ "id": number, "website_id": number, "status": string, "progress": number, "message": string, "error": string, "auto_analyze": boolean, "analysis_run_id": number | null }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Scan not found" }` wanneer de scan niet bestaat.

### get_scan_analysis_status

- Doel: geeft één pollbaar statusscherm voor de volledige workflow uit `scan_and_analyze_website`: websiteprofiel, scanstatus, gekoppelde of laatste analyse-run en een `ready` vlag.
- Inputschema: `{ "scan_id": number }`
- Outputschema: `{ "website": object, "scan": object, "analysis": AnalysisRunRead | null, "ready": boolean }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Scan not found" }` wanneer de scan niet bestaat.

### search_company_data

- Doel: semantisch zoeken in gecrawlde documenten en chunks voor compacte, brongekoppelde LLM-context.
- Inputschema: `{ "query": string, "website_id"?: number | null, "limit"?: number }`
- Outputschema: `{ "results": [{ "document_id": number, "website_id": number, "company_name": string, "source_url": string, "title": string, "summary": string, "content_type": string, "score": number }] }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: validatiefouten op lege query of ongeldige limiet; operationele fouten als standaard MCP error.

### get_company_profile

- Doel: geeft een brede contextsnapshot van een bedrijf terug, inclusief websiteprofiel en documentensamenvattingen.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "id": number, "url": string, "company_name": string, "logo_url": string, "documents": [{ "id": number, "title": string, "url": string, "summary": string }] }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat.

### list_analysis_prompts

- Doel: toont de beheerbare promptketen waarmee de agentische analyse werkt.
- Inputschema: `{}`
- Outputschema: `{ "prompts": [{ "prompt_id": string, "title": string, "description": string, "sort_order": number, "is_system_prompt": boolean, "updated_at": datetime }] }`
- Autorisatie: API token met minimaal `read`; wijzigen blijft via REST/UI beheer en vereist admin.
- Foutgedrag: operationele fouten als standaard MCP error.

### run_company_analysis

- Doel: draait de bedrijfsanalyseketen voor een website op basis van profielmetadata, samenvattingen en semantische context.
- Inputschema: `{ "website_id": number }`
- Outputschema: `AnalysisRunRead` met `id`, `website_id`, `status`, `model`, `extracted_variables`, `error`, timestamps en `jobs`.
- Autorisatie: API token met minimaal `execute`.
- Foutgedrag: `{ "error": "Website not found" }` wanneer de website niet bestaat; providerfouten worden in run/job `error` vastgelegd.

### get_company_analysis

- Doel: haalt een opgeslagen analyse-run op zonder opnieuw AI-kosten of wachttijd te veroorzaken.
- Inputschema: `{ "analysis_id": number }`
- Outputschema: `AnalysisRunRead`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer de analyse niet bestaat.

### generate_company_scenarios

- Doel: maakt scenario-klare kansen uit de laatste opgeslagen bedrijfsanalyse.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "website_id": number, "analysis_id": number, "scenarios": [{ "title": string, "input": string, "source_prompt": string }] }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer er nog geen analyse beschikbaar is.

### generate_poc_brief

- Doel: maakt een compacte PoC-briefing met profiel, uitdagingen, waardekansen en technische haakjes.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "website_id": number, "analysis_id": number, "brief": { "bedrijf": string, "plaats": string, "regio": string, "profiel": string, "uitdagingen": string, "waardekansen": string, "technische_haakjes": string } }`
- Autorisatie: API token met minimaal `read`.
- Foutgedrag: `{ "error": "Analysis not found" }` wanneer er nog geen analyse beschikbaar is.

## Toekomstige tool: reset_website_data

- Doel: verwijdert alle scan- en analysedata van een bestaande website, terwijl het website-record en de beheerinstellingen blijven bestaan.
- Inputschema: `{ "website_id": number }`
- Outputschema: `{ "status": "reset" }`
- Autorisatie: alleen API token met `admin`.
- Foutgedrag: `404` wanneer de website niet bestaat; operationele fouten worden als standaard API/MCP-fout teruggegeven.
