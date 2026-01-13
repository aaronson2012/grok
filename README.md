# Grok Discord Bot

A Discord bot integrated with OpenRouter (AI) and Perplexity AI (Real-time web search), featuring multimodal capabilities and persona management.

## Features

- **AI Chat**: powered by OpenRouter (compatible with OpenAI API).
- **Web Search**: Real-time web search using Perplexity AI Search API, accessible via automatic tool calling.
- **Multimodal**: Supports image inputs (including GIFs).
- **Personas**: Customizable personas per guild.
- **Context Awareness**: Intelligent message history management and time-based context resetting.

## Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/aaronson2012/grok.git
    cd grok
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables**:
    Create a `.env` file in the root directory with the following keys:
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    OPENROUTER_API_KEY=your_openrouter_key
    OPENROUTER_MODEL=your_preferred_model_id (e.g., anthropic/claude-3-opus)
    PERPLEXITY_API_KEY=your_perplexity_api_key
    ```

4.  **Run the Bot**:
    ```bash
    python main.py
    ```

## Testing

Run the test suite using `pytest`:

```bash
export PYTHONPATH=$PYTHONPATH:.
pytest tests/
```

## Project Structure

- `src/cogs/`: Discord bot cogs (commands and listeners).
- `src/services/`: Core business logic (AI, Search, Database, Tools).
- `src/utils/`: Utility functions.
- `tests/`: Unit tests.
