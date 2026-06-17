# Lumen

A lightweight analytics platform for Claude Code. Track how your team uses skills, tools, and workflows — across any number of projects and organizations.

## Deploy to Railway

1. Go to [railway.app](https://railway.app) and create a new project
2. **Add a service** → Deploy from GitHub repo → select `Aark2g-Labs/lumen`
3. **Add a service** → Database → PostgreSQL
4. Railway automatically injects `DATABASE_URL` — no extra config needed
5. Optionally set `ADMIN_SECRET` in the app service's environment variables to restrict org creation
6. Once deployed, visit `https://your-app.railway.app/setup` to create your first org

## Local development

```bash
# Create a local Postgres DB
createdb lumen

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env   # edit DATABASE_URL if needed

# Run
uvicorn app.main:app --reload --port 8765
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (set automatically by Railway) |
| `ADMIN_SECRET` | No | If set, required when creating orgs via `/setup` or `POST /orgs` |

## Getting started

1. Visit `/setup` — enter your org name, copy the API key shown
2. Visit `/login` — paste the API key to access your dashboard
3. Add the hook below to start tracking skill usage

## Claude Code hook

Add this to `.claude/settings.json` (project or global `~/.claude/settings.json`):

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Skill",
      "command": "skill=$(cat | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('skill','unknown'))\" 2>/dev/null || echo unknown); curl --max-time 2 -s -X POST https://your-app.railway.app/events -H 'Content-Type: application/json' -H 'Authorization: Bearer $LUMEN_API_KEY' -d \"{\\\"event\\\": \\\"skill_used\\\", \\\"properties\\\": {\\\"skill\\\": \\\"$skill\\\"}, \\\"user\\\": \\\"$(git config user.email 2>/dev/null)\\\", \\\"project\\\": \\\"$(basename $(git rev-parse --show-toplevel 2>/dev/null) 2>/dev/null)\\\"}\" > /dev/null 2>&1 &"
    }]
  }
}
```

Set `LUMEN_API_KEY=your_api_key` in each developer's shell environment (e.g. `~/.zshrc`).

## Event schema

```json
{
  "event": "skill_used",
  "properties": { "skill": "jira-ticket" },
  "user": "kshitiz@company.com",
  "project": "my-repo",
  "timestamp": "2026-06-17T14:00:00Z"
}
```

All fields except `event` are optional. `properties` is free-form JSON.

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET/POST` | `/setup` | None* | Create an org, get an API key |
| `POST` | `/orgs` | None* | Create an org (JSON API) |
| `POST` | `/events` | `Bearer <api_key>` | Ingest an event |
| `GET` | `/login` | — | Sign in with API key |
| `GET` | `/dashboard` | Cookie session | View analytics dashboard |
| `GET` | `/health` | None | Health check |

\* If `ADMIN_SECRET` is set, org creation requires it.
