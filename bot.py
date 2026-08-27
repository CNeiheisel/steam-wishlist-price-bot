import os
import json
import requests
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv

load_dotenv(override=True)

# Environment Variabl,es
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
STEAM_API_KEY = os.environ.get("STEAM_API_KEY")
ITAD_API_KEY = os.environ.get("ITAD_API_KEY")
STEAM_ID64 = os.environ.get("STEAM_ID64")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
DISCORD_USER_ID = os.environ.get("DISCORD_USER_ID", "")
CHECK_INTERVAL_HOURS = float(os.environ.get("CHECK_INTERVAL_HOURS", "6"))


PRICES_FILE = "prices.json"


def load_prices() -> dict:
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_prices(prices: dict) -> None:
    with open(PRICES_FILE, "w") as f:
        json.dump(prices, f, indent=2)


# Calling Steam

def fetch_wishlist_appids(steam_id64: str) -> list[int]:
    url = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
    resp = requests.get(url, params={"steamid": steam_id64, "key": STEAM_API_KEY}, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("response", {}).get("items", [])
    return [item["appid"] for item in items]


def fetch_steam_name_and_price(appid: int) -> tuple[str, float | None, str]:
    """Returns (name, price_in_dollars_or_None, display_string)"""
    url = "https://store.steampowered.com/api/appdetails"
    resp = requests.get(
        url,
        params={"appids": appid, "cc": "us", "filters": "basic,price_overview"},
        timeout=15,
    )
    resp.raise_for_status()
    entry = resp.json().get(str(appid))
    if not entry or not entry.get("success"):
        return (f"App {appid}", None, "N/A")
    data = entry["data"]
    name = data.get("name", f"App {appid}")
    price_overview = data.get("price_overview")
    if price_overview:
        cents = price_overview["final"]
        dollars = cents / 100.0
        return (name, dollars, f"${dollars:.2f}")
    return (name, None, "Free / Not for sale")


def fetch_itad_ids(appids: list[int]) -> dict[int, str | None]:
    if not appids:
        return {}
    url = f"https://api.isthereanydeal.com/lookup/id/shop/61/v1?key={ITAD_API_KEY}"
    body = [f"app/{a}" for a in appids]
    resp = requests.post(url, json=body, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {a: data.get(f"app/{a}") for a in appids}


def fetch_all_time_lows(itad_ids: list[str]) -> dict[str, float | None]:
    if not itad_ids:
        return {}
    url = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US"
    resp = requests.post(url, json=itad_ids, timeout=15)
    resp.raise_for_status()
    result = {}
    for entry in resp.json():
        low = entry.get("historyLow", {}).get("all")
        result[entry["id"]] = low["amount"] if low else None
    return result


def check_wishlist() -> list[dict]:
    """Runs a full check and returns a list of dicts for games currently at or below
    their all-time low price. Each game is only re-notified once per new dip to that
    low (i.e. it won't re-fire every single check while the price stays flat)."""
    appids = fetch_wishlist_appids(STEAM_ID64)
    if not appids:
        return []

    prices = load_prices()
    hits = []

    name_price_map = {a: fetch_steam_name_and_price(a) for a in appids}

    itad_id_map = fetch_itad_ids(appids)
    valid_itad_ids = [i for i in itad_id_map.values() if i]
    lows = fetch_all_time_lows(valid_itad_ids)

    for appid in appids:
        name, current_price, display_price = name_price_map[appid]
        if current_price is None:
            continue

        key = str(appid)
        prior = prices.get(key, {})
        already_notified = prior.get("notified_low", False)

        itad_id = itad_id_map.get(appid)
        low_amount = lows.get(itad_id) if itad_id else None
        low_display = f"${low_amount:.2f}" if low_amount is not None else "Unknown"

        is_at_low = low_amount is not None and current_price <= low_amount

        if is_at_low and not already_notified:
            hits.append({
                "name": name,
                "current_price": current_price,
                "display_price": display_price,
                "all_time_low": low_display,
            })

        prices[key] = {
            "price": current_price,
            # Reset the flag once the price rises back above the low, so a future
            # dip back down to (or below) the low will notify again.
            "notified_low": is_at_low,
        }

    save_prices(prices)
    return hits


# Discord Integration

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

_is_first_run = True


MENTION = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else ""


async def run_check_and_report(destination) -> None:
    """Runs check_wishlist() and sends results to the given channel/context."""
    try:
        hits = check_wishlist()
    except Exception as e:
        await destination.send(f"Error checking wishlist: {e}")
        return

    if not hits:
        await destination.send("Nothing is currently at its all-time low.")
        return

    for hit in hits:
        await destination.send(
            f"{MENTION}🏷️ **{hit['name']}** just hit its all-time low: "
            f"{hit['display_price']} (all-time low: {hit['all_time_low']})"
        )


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not price_check_loop.is_running():
        # tasks.loop runs its function immediately when start() is called, then
        # again every CHECK_INTERVAL_HOURS after that — so this alone gives us a
        # check-on-startup for free, no separate call needed here.
        price_check_loop.start()


@tasks.loop(hours=CHECK_INTERVAL_HOURS)
async def price_check_loop():
    global _is_first_run

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found, check CHANNEL_ID")
        return

    if _is_first_run:
        await channel.send("Bot started — running an initial wishlist check...")
        _is_first_run = False

    await run_check_and_report(channel)


@bot.command(name="checknow")
async def checknow(ctx):
    await ctx.send("Checking wishlist now...")
    await run_check_and_report(ctx)


if __name__ == "__main__":
    missing = [
        name for name, val in [
            ("DISCORD_TOKEN", DISCORD_TOKEN),
            ("STEAM_API_KEY", STEAM_API_KEY),
            ("ITAD_API_KEY", ITAD_API_KEY),
            ("STEAM_ID64", STEAM_ID64),
        ] if not val
    ]
    if missing or CHANNEL_ID == 0:
        raise SystemExit(f"Missing required environment variables: {missing + (['CHANNEL_ID'] if CHANNEL_ID == 0 else [])}")

    bot.run(DISCORD_TOKEN)
