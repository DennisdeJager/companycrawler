# Backlog

## Done

- [x] AI Models uit de navigatie verwijderd en gebruikersbeheer uitgebreid met toevoegen, wijzigen en verwijderen via compacte modals.
- [x] Settings uitgebreid met centrale modelselecties voor summary, embeddings en agent-analyse, inclusief aanbevolen modellen uit de AI-catalogus.
- [x] Development login met `admin@example.com` verwijderd; eerste Google gebruiker wordt admin en latere gebruikers blijven guest tot roltoekenning.
- [x] Actieve website-selectie wordt per gebruiker onthouden na een page reload.
- [x] Settings opgesplitst in tabbladen voor providers, Google authenticatie, crawl instellingen en promptbeheer.
- [x] Agentische analyseflow met beheerbare prompts, analyse-opslag, REST/MCP tools en Analyse UI toegevoegd.
- [x] MCP JSON-RPC endpoint geeft nu een nette parse error terug bij malformed JSON.
- [x] MCP semantische zoekopdracht gerepareerd door de SQLAlchemy join expliciet te maken.
- [x] Knowledge Graph mindmap vervangen door inklapbare, sleepbare en zoombare website explorer.
- [x] Mailto-links uit crawls geweerd, duplicate graph nodes op content-hash samengevoegd en content inspector scrollbaar gemaakt.
- [x] Mailto-adressen blijven beschikbaar in crawltekst en vector chunks zonder als losse pagina's te worden gecrawld.
- [x] Dashboard scanbediening voor starten, pauzeren en stoppen toegevoegd; reset verwijdert website crawl-data inclusief graph chunks.
- [x] Analysejobs draaien live op de achtergrond met actuele jobstatus, duurweergave en verwijderbare jobresultaten.
- [x] Websitebeheer gebruikt modals voor nieuwe en bestaande websites; reset staat bij de dashboard-scanbediening.

- [x] Knowledge Graph mindmap, crawler deduplicatie, scanstatistieken en instelbare parallelle crawlverwerking toegevoegd.
- [x] Bedrijfslogo-detectie, Smawa huisstijl-logo, dark theme en hiërarchische dashboard tree toegevoegd.
- [x] Vector-deduplicatie op content-hash, meerlagige mindmap, sticky inspector en rijkere scanvisuals toegevoegd.
- [x] V1 plan uitgewerkt.
- [x] Basis monorepo scaffold toegevoegd.
- [x] FastAPI REST, MCP manifest en OpenAPI docs toegevoegd.
- [x] React webconsole toegevoegd volgens goedgekeurde UI-richting.
- [x] Docker compose deployment toegevoegd.
- [x] ALM manifest en compose webservice-naam toegevoegd.
- [x] MCP server geschikt gemaakt voor ChatGPT en andere MCP/LLM-clients via JSON-RPC `initialize`, `tools/list` en `tools/call`.

## Next

- [ ] Productie Google OAuth client configureren.
- [ ] OpenAI/OpenRouter keys configureren.
- [ ] Eerste echte scan uitvoeren in dev container.
- [ ] GitHub repository `DennisdeJager/companycrawler` aanmaken/pushen.
- [ ] Caddy mapping `companycrawler.smawa.nl` activeren.

