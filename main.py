import os
import re
import requests
from bs4 import BeautifulSoup
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
# paste your discord bot token here (or keep it in secrets)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# SCRAPER LOGIC
# ---------------------------------------------------------
def scrape_mun_website(url: str) -> dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return {"error": f"failed to fetch site ({url}): {str(e)}"}

    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.get_text()

    title = soup.title.string.strip() if soup.title else "model un conference"
    
    # dates / timing
    dates = "check website for dates"
    date_patterns = [
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:-\d{1,2})?,? \d{4}',
        r'\d{1,2}(?:-\d{1,2})? (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}'
    ]
    for pattern in date_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            dates = match.group(0)
            break

    # pricing
    prices = re.findall(r'(\$\d+|\d+\s?USD|\d+\s?EUR|\d+\s?GBP)', page_text)
    pricing = ", ".join(list(set(prices))[:4]) if prices else "refer to website for fees."

    # committees
    committees = []
    keywords = ["DISEC", "SOCHUM", "SPECPOL", "UNSC", "ECOSOC", "ICJ", "HCC", "Crisis", "UNHRC"]
    for kw in keywords:
        if kw in page_text:
            committees.append(kw)

    for header in soup.find_all(['h2', 'h3', 'h4', 'a']):
        text = header.get_text().strip()
        if ("committee" in text.lower() or "council" in text.lower()) and len(text) < 50:
            if text not in committees:
                committees.append(text)

    committees_formatted = "\n• " + "\n• ".join(committees[:8]) if committees else "see website for full list."

    return {
        "title": title,
        "url": url,
        "dates": dates,
        "pricing": pricing,
        "committees": committees_formatted,
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Flag_of_the_United_Nations.svg/1200px-Flag_of_the_United_Nations.svg.png"
    }

# ---------------------------------------------------------
# BOT EVENTS & COMMANDS
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print(f"logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"failed to sync commands: {e}")

@bot.tree.command(name="mun", description="scrape and package info for a model un conference website")
@app_commands.describe(url="the url of the mun conference website")
async def mun_command(interaction: discord.Interaction, url: str):
    # defer response so discord doesn't time out while scraping
    await interaction.response.defer(thinking=True)
    
    data = scrape_mun_website(url)

    if "error" in data:
        await interaction.followup.send(f"❌ {data['error']}")
        return

    embed = discord.Embed(
        title=f"🇺🇳 {data['title']}",
        url=data['url'],
        description="here are the details retrieved from the conference website:",
        color=0x3498DB
    )
    embed.set_thumbnail(url=data['icon_url'])
    embed.add_field(name="📅 Dates & Timing", value=data['dates'], inline=True)
    embed.add_field(name="💵 Pricing / Fees", value=data['pricing'], inline=True)
    embed.add_field(name="🏛️ Committees Offered", value=data['committees'], inline=False)
    embed.set_footer(
        text="Model UN Server Automation • Info Package",
        icon_url="https://cdn-icons-png.flaticon.com/512/25/25231.png"
    )

    await interaction.followup.send(embed=embed)

# ---------------------------------------------------------
# START BOT
# ---------------------------------------------------------
if __name__ == "__main__":
    bot.run(BOT_TOKEN)