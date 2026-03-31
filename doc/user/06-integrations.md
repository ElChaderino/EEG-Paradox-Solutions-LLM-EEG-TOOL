# User Manual 06 — Integrations

## Objective

Configure optional services: web search (Google, DuckDuckGo, SearXNG), Skye (remote Ollama), Discord.

## Google Programmable Search (primary web)

**Purpose:** When `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX` are set, `web_search` and the web leg of `deep_research` query **Google** first and merge **DuckDuckGo** as secondary (unless `WEB_SEARCH_FALLBACK_DDG=false`). This uses Google’s supported Custom Search JSON API (not HTML scraping).

**Configuration:**

1. In [Google Cloud Console](https://console.cloud.google.com/), enable **Custom Search API** and create an API key.
2. In [Programmable Search Engine](https://programmablesearchengine.google.com/), create a search engine (typically “Search the entire web” or your allowed sites). Copy the **Search engine ID** (cx).
3. Set in `.env`:

   ```
   GOOGLE_CSE_API_KEY=your_key
   GOOGLE_CSE_CX=your_cx
   WEB_SEARCH_FALLBACK_DDG=true
   ```

**Note:** Free tier has a daily query quota; monitor usage in Cloud Console. If keys are unset, behavior falls back to DuckDuckGo only (or SearXNG when `SEARXNG_URL` is set).

## SearXNG (web search)

**Purpose:** When `SEARXNG_URL` is set, it **replaces** the Google+DuckDuckGo path and supplies results to `web_search` from your self-hosted instance.

**Configuration:**

1. Deploy SearXNG (commonly Docker) on a host reachable from the Paradox host.
2. Set in `.env`:

   ```
   SEARXNG_URL=http://host:port
   ```

   No trailing slash required; code normalizes.

**Verification:** Open `{SEARXNG_URL}/search?q=test&format=json` in a browser or curl; expect JSON.

**Privacy note:** SearXNG aggregates third-party search engines per your instance configuration; data leaves your LAN only as defined by that stack.

## Skye (heavy inference)

**Purpose:** Second-pass text generation when local agent confidence remains below `confidence_threshold` and `SKYE_URL` is non-empty.

**Configuration:**

1. On the remote host, run Ollama with API bound to a LAN address (firewall rules **shall** restrict sources).
2. Set:

   ```
   SKYE_URL=http://skye-host:11434
   SKYE_MODEL=mistral-small:22b
   ```

3. Ensure the model name exists on the remote: `ollama pull` on that machine.

**Security:** Treat `SKYE_URL` as sensitive infrastructure. Prefer TLS termination or VPN if traffic crosses untrusted segments.

## Discord

### Tool: `send_discord_message`

Requires `DISCORD_TOKEN` and `DISCORD_CHANNEL_ID` in `.env`. Uses Discord REST API (Bot token) to post to the channel.

**Shall:** Use a bot token with minimum required intents and channel scope.

### Script: `scripts/discord_bot.py`

Relays messages from a configured channel to `POST /agent`.

**Environment:**

- `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID` (required).
- `HEX_API` (optional; default `http://127.0.0.1:8765`).

**Intent:** Message content intent **shall** be enabled in the Discord developer portal for the bot to read channel text.

## LoRa mesh

Tool `lora_send` is a **stub**. Hardware integration is not implemented in this repository.

Next: `user/07-troubleshooting.md`.
