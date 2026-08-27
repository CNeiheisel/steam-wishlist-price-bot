# Steam Wishlist Price Alert Bot

A Discord bot that monitors a Steam wishlist and sends a targeted notification the moment a game reaches its **all-time lowest price**. Since Steam doesn't track historical pricing itself, the bot cross-references live price data from Steam's Web API against historical low data from the [IsThereAnyDeal](https://isthereanydeal.com/) API — so you know when a sale is actually the best a game has ever been, not just a discount.

## Features

- Pulls your Steam wishlist automatically via Steam's Web API
- Fetches current pricing per game from Steam's storefront API
- Cross-references each game's all-time low price via the IsThereAnyDeal API
- Notifies you in Discord — with a targeted `@mention` — only when a game is at or below its all-time low
- **Deduplicated alerts**: won't repeatedly notify you for the same sale on every scheduled check, only when the price newly drops to (or below) the low
- Runs an initial check automatically on startup, then on a configurable interval
- Manual `!checknow` command to trigger an on-demand check

## Architecture

- **Data layer** — small functions, each responsible for exactly one API call (Steam wishlist, Steam pricing, ITAD ID lookup, ITAD historical low)
- **Orchestration layer** — `check_wishlist()` combines the data sources and applies the alert threshold + deduplication logic
- **Delivery layer** — a `discord.py` bot that schedules the orchestration function on a timer and formats/sends results

State (last known price and whether you've already been notified for a given low) is persisted locally to `prices.json` between runs.

## Prerequisites

- Python 3.10+
- A [Steam Web API key](https://steamcommunity.com/dev/apikey)
- An [IsThereAnyDeal API key](https://isthereanydeal.com/apps/my/)
- A Discord bot (see setup below)
- Your Steam profile's wishlist set to **Public**

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/YOUR_USERNAME/steam-wishlist-price-bot.git
   cd steam-wishlist-price-bot
   ```

2. Create a Discord bot and invite it to your server:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
   - **Bot** tab → **Reset Token** → copy it (this is `DISCORD_TOKEN`)
   - Still on the **Bot** tab, under **Privileged Gateway Intents**, enable **Message Content Intent** and save
   - **OAuth2 → URL Generator**: check the `bot` scope, and permissions `Send Messages` + `Read Message History`
   - Open the generated URL and invite the bot to your server
   - In Discord, enable **Settings → Advanced → Developer Mode**, then right-click the channel you want alerts in → **Copy Channel ID** (this is `CHANNEL_ID`), and right-click your own name → **Copy User ID** (this is `DISCORD_USER_ID`, used to `@mention` you on alerts)

3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/Scripts/activate   # Windows (Git Bash)
   # source venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root with the following:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   STEAM_API_KEY=your_steam_web_api_key
   ITAD_API_KEY=your_isthereanydeal_api_key
   STEAM_ID64=your_steamid64
   CHANNEL_ID=your_discord_channel_id
   DISCORD_USER_ID=your_discord_user_id
   CHECK_INTERVAL_HOURS=6
   ```

5. Run it:
   ```bash
   python bot.py
   ```

## Usage

- On startup, the bot posts a message confirming it's running and performs an initial check.
- Every `CHECK_INTERVAL_HOURS`, it checks again automatically.
- Type `!checknow` in the bot's channel to trigger a check immediately.
- You'll only be `@mentioned` when a game is actually at or below its all-time low — routine status updates stay silent.

## Known limitations

- Single-user: hardcoded to one `STEAM_ID64`, not per-Discord-user
- No retry/backoff on a failed API call — a failed check is skipped and reported, not retried
- Requires the bot's host machine to be running; no built-in cloud deployment

## Tech stack

Python · discord.py · Steam Web API · IsThereAnyDeal API · python-dotenv
