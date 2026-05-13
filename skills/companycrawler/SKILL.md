---
name: companycrawler
description: Start companycrawler scans, inspect scan status, and retrieve public company marketing profile data through the companycrawler API or MCP server.
---

# Companycrawler Skill

Use this skill when another app or agent needs to collect or query public company website data.

## Capabilities

- Start a scan for a known website.
- Check scan status and progress.
- Retrieve company profile metadata and document summaries.
- Search crawled company data semantically.

## API-first workflow

1. Create or find the website through `GET /api/websites` and `POST /api/websites`.
2. Start a scan with `POST /api/scans`.
3. Poll `GET /api/scans/{scan_id}` until `completed` or `failed`.
4. Retrieve data with `GET /api/websites/{website_id}/documents` or `POST /api/search`.

## MCP tools

The embedded MCP manifest is available at `/mcp` and exposes:

- `list_websites`
- `start_scan`
- `get_scan_status`
- `search_company_data`
- `get_company_profile`

## Safety scope

Only collect public website data for marketing intelligence. Do not use this skill for security scanning, vulnerability discovery, authentication bypassing, or form attack automation.

