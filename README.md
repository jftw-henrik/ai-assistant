# Henrik Assistant

AI agent API that receives free-form text, decides which tool to call, and executes it.

## Requirements

- Python 3.12+
- A [Groq API key](https://console.groq.com/keys)

## Setup

```bash
cd "AI Assistant"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set your `GROQ_API_KEY`.

## Run

Local development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Production-style start (uses `PORT`, defaults to `8000`):

```bash
sh scripts/start.sh
```

API docs: http://127.0.0.1:8000/docs

## Usage

`POST /capture` is optimized for Apple Shortcuts. Send dictated text, get a plain-text confirmation.

```bash
curl -X POST http://127.0.0.1:8000/capture \
  -H "Content-Type: application/json" \
  -d '{"text": "Interview Friday at 14 with NZM"}'
```

Response:

```
✅ Added to Google Calendar.
```

More examples:

| Input | Response |
|-------|----------|
| `Remember to call electrician.` | `✅ Added to Google Tasks.` |
| `Idea: Cubase MCP` | `💡 Saved as an idea.` |

Errors return JSON (e.g. HTTP 502). Success always returns plain text.

### Apple Shortcuts

1. **Dictate Text** → **Get Contents of URL**
2. URL: `http://<your-mac-ip>:8000/capture`
3. Method: `POST`
4. Request Body: JSON — `{"text": "Dictated Text"}`
5. Show the response in a notification or speak it aloud

The agent selects and runs one tool internally. Example server console output:

```
create_calendar_event(title='NZM Interview', date='2026-07-03T14:00', event_id='abc123xyz')
```

## Google setup

1. Create an OAuth 2.0 **Desktop app** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Enable the **Google Calendar API** and **Google Tasks API** for the project.
3. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`.

   **Important:** use a Desktop client, not a Web client. A Web client will return HTTP 400.

4. Run the one-time OAuth flow:

```bash
python scripts/google_oauth_setup.py
```

5. Copy the printed `GOOGLE_REFRESH_TOKEN` into `.env`.

The script requests Calendar and Tasks scopes with `access_type=offline` and `prompt=consent`.
Re-run the OAuth script if you previously authorized Calendar only.

### Calendar events

- visibility: `private`
- reminders: 1 week, 1 day, and 1 hour before
- duration: 1 hour (unless an end time is provided)

### Tasks

`create_todo` creates tasks in your default Google Tasks list with optional notes and due date.

Example console output:

```
create_todo(title='Call electrician', task_id='abc123')
```

## Tools

| Tool                    | When used                          |
|-------------------------|------------------------------------|
| `create_calendar_event` | Meetings, appointments, interviews (Google Calendar) |
| `create_todo`           | Tasks and reminders (Google Tasks) |
| `save_idea`             | Ideas and notes                    |
| `create_project`        | Multi-step initiatives             |

Tools save records to a local SQLite database and print to the console.

## Verify saved items

After dictating from your iPhone, open these in a browser:

- http://127.0.0.1:8000/todos
- http://127.0.0.1:8000/ideas
- http://127.0.0.1:8000/projects
- http://127.0.0.1:8000/calendar-events

Each returns a JSON list, newest first.

## Project layout

```
app/
  main.py                    # FastAPI routes
  config.py                  # Environment settings
  models/capture.py          # Request schema
  models/records.py          # Response schemas for GET endpoints
  services/agent.py          # Groq agent with tool calling
  services/confirmations.py  # Plain-text Shortcut confirmations
  db/
    database.py              # SQLite connection and schema
    repository.py            # Insert and list operations
  integrations/
    google_auth.py         # Shared Google OAuth credentials
    google_calendar.py     # Google Calendar API client
    google_tasks.py        # Google Tasks API client
  tools/
    base.py                  # Tool interface
    implementations.py       # Tool implementations (print + save)
    registry.py              # Tool registry and dispatch
data/
  henrik_assistant.db        # Local SQLite (when DATABASE_PATH is set)
railway.json                 # Railway deploy config
scripts/
  start.sh                   # Production startup command
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | yes | — | Groq API key for the AI agent |
| `GROQ_MODEL` | no | `llama-3.3-70b-versatile` | Groq chat model |
| `PORT` | no | `8000` | HTTP port (`scripts/start.sh`; Railway sets this automatically) |
| `DATABASE_PATH` | no | `/tmp/henrik_assistant.db` | SQLite database file path |
| `GOOGLE_CLIENT_ID` | yes* | — | Google OAuth Desktop client ID |
| `GOOGLE_CLIENT_SECRET` | yes* | — | Google OAuth Desktop client secret |
| `GOOGLE_REFRESH_TOKEN` | yes* | — | Google OAuth refresh token |
| `GOOGLE_CALENDAR_ID` | no | `primary` | Target Google Calendar |
| `GOOGLE_CALENDAR_TIMEZONE` | no | `Europe/Stockholm` | Timezone for calendar events |

\* Required for `create_calendar_event` and `create_todo`. Ideas and projects work without Google credentials.

For local development, set `DATABASE_PATH=data/henrik_assistant.db` in `.env` to persist data in the project directory.

## Railway deployment

### Checklist

- [ ] Create a new Railway project and connect this repository
- [ ] Set **Root Directory** if the repo is not at the project root
- [ ] Add environment variables in Railway:
  - [ ] `GROQ_API_KEY`
  - [ ] `GOOGLE_CLIENT_ID`
  - [ ] `GOOGLE_CLIENT_SECRET`
  - [ ] `GOOGLE_REFRESH_TOKEN`
  - [ ] `GOOGLE_CALENDAR_TIMEZONE` (optional)
  - [ ] `GROQ_MODEL` (optional)
- [ ] Do **not** set `PORT` — Railway injects it automatically
- [ ] Understand SQLite is ephemeral on Railway unless you attach a volume:
  - Default path `/tmp/henrik_assistant.db` is reset on redeploy
  - For persistence, mount a Railway volume and set `DATABASE_PATH` to the mount path (e.g. `/data/henrik_assistant.db`)
- [ ] Deploy — Railway uses `railway.json` → `sh scripts/start.sh`
- [ ] Copy the public Railway URL for Apple Shortcuts: `https://<app>.up.railway.app/capture`
- [ ] Verify health: `GET https://<app>.up.railway.app/health`
- [ ] Test capture:

```bash
curl -X POST https://<app>.up.railway.app/capture \
  -H "Content-Type: application/json" \
  -d '{"text": "Idea: test from Railway"}'
```

### Startup command

```bash
sh scripts/start.sh
```

Equivalent to:

```bash
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```
