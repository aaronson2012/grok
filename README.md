# Grok

> **Why "Grok"?** Because saying "@Grok is this true?" is the funniest shit ever. People say it all the time on X. So naturally, this bot had to be named Grok.

A multi-platform AI chat bot for Discord and Telegram, powered by OpenRouter and Perplexity AI.

## Features

- **AI Chat** — Conversational AI via OpenRouter (OpenAI-compatible API). Supports any model available on OpenRouter.
- **Web Search** — Real-time web search using Perplexity AI, triggered automatically via tool calling.
- **Calculator** — Built-in math evaluation for arithmetic and functions (sin, cos, sqrt, etc.).
- **Multimodal** — Supports image inputs including GIFs.
- **Personas** — Customizable system prompts per guild/chat.
- **Daily Digest** — Scheduled news digests with per-user topics, timezone support, and duplicate detection.
- **Context Awareness** — Intelligent message history management with time-based context resetting.

## Platforms

| Platform | Entry Point | Deployment |
|----------|-------------|------------|
| Discord | `bot_discord.py` | `fly.discord.toml` |
| Telegram | `bot_telegram.py` | `fly.telegram.toml` |

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/aaronson2012/grok.git
cd grok
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file:

```env
# Required for Discord bot
DISCORD_TOKEN=your_discord_bot_token

# Required for Telegram bot
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_ADMIN_IDS=123456789,987654321  # Comma-separated admin user IDs

# Required for AI
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=google/gemini-3-flash-preview  # Or any OpenRouter model

# Required for web search
PERPLEXITY_API_KEY=your_perplexity_api_key

# Optional
DATABASE_PATH=data/grok.db
DEBUG_GUILD_IDS=123456789  # For faster slash command sync during development
```

### 3. Run

```bash
# Discord
python bot_discord.py

# Telegram
python bot_telegram.py
```

## Discord Commands

### Chat
The bot responds when mentioned or replied to.

### Personas
- `/persona` — Select active persona
- `/persona create <name> <prompt>` — Create custom persona
- `/persona delete` — Delete a persona
- `/persona current` — View current persona

### Digest (Daily News)
- `/digest topics add <topic>` — Add a topic to your digest
- `/digest topics remove <topic>` — Remove a topic
- `/digest topics list` — List your topics
- `/digest config time <HH:MM>` — Set your daily digest time
- `/digest config timezone <tz>` — Set your timezone (e.g., America/New_York)
- `/digest config channel <#channel>` — (Admin) Set digest output channel
- `/digest config max_topics <n>` — (Admin) Set per-user topic limit
- `/digest now` — Trigger digest immediately

### Admin
- `/memory view` — View conversation memory
- `/memory clear` — Clear conversation memory
- `/logs view` — View error logs
- `/logs clear` — Clear error logs

## Telegram Commands

- `/start`, `/help` — Get started
- `/chat <message>` — Chat with the bot (also responds to mentions/replies)
- `/persona`, `/persona_create`, `/persona_delete`, `/persona_current` — Persona management
- `/digest_add`, `/digest_remove`, `/digest_list` — Digest topics
- `/digest_time`, `/digest_timezone`, `/digest_now` — Digest settings
- `/memory_view`, `/memory_clear`, `/logs_view`, `/logs_clear` — Admin commands

## Testing

```bash
pytest tests/
```

## Project Structure

```
├── bot_discord.py          # Discord bot entry point
├── bot_telegram.py         # Telegram bot entry point
├── src/
│   ├── bot.py              # Discord bot initialization
│   ├── config.py           # Environment configuration
│   ├── cogs/               # Discord command handlers
│   │   ├── admin.py
│   │   ├── chat.py
│   │   ├── digest.py
│   │   └── settings.py
│   ├── telegram_handlers/  # Telegram command handlers
│   │   ├── admin.py
│   │   ├── chat.py
│   │   ├── digest.py
│   │   └── settings.py
│   ├── services/
│   │   ├── ai.py           # OpenRouter integration
│   │   ├── db.py           # SQLite database
│   │   ├── search.py       # Perplexity search
│   │   ├── tools.py        # Tool registry (search, calculator)
│   │   └── emoji_manager.py
│   └── utils/
│       ├── calculator.py   # Safe math expression evaluator
│       ├── chunker.py      # Message chunking for Discord limits
│       └── decorators.py   # Retry decorators
├── tests/                  # Unit tests
├── fly.discord.toml        # Fly.io config for Discord bot
└── fly.telegram.toml       # Fly.io config for Telegram bot
```

## Deployment

Deploy to [Fly.io](https://fly.io):

```bash
# Discord
fly deploy -c fly.discord.toml

# Telegram
fly deploy -c fly.telegram.toml
```
