import os
import re
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# ADVANCED JS-ENABLED SCRAPER
# ---------------------------------------------------------
async def fetch_rendered_html(url: str) -> str:
    """Renders the website using a headless browser to execute JavaScript."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # Wait 3s for JS components/tables to render
            content = await page.content()
        except Exception:
            content = ""
        finally:
            await browser.close()
        return content

def scrape_mun_website_smart(url: str, html_content: str) -> dict:
    if not html_content:
        return {"error": f"Failed to render website or request timed out ({url})"}

    soup = BeautifulSoup(html_content, 'html.parser')
    page_text = soup.get_text(separator=' ')

    # 1. Conference Title
    title = soup.title.string.strip() if soup.title else "Model UN Conference"
    title = re.sub(r'\s+', ' ', title)

    # 2. Smart Date Matching (Supports multi-day ranges across months)
    dates = "Check website for dates"
    date_patterns = [
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\s*(?:–|-|to)\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?[a-z]* \d{1,2},? \d{4}',
        r'\d{1,2}\s*(?:–|-|to)\s*\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}',
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}'
    ]
    for pattern in date_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            dates = match.group(0).strip()
            break

    # 3. Smart Pricing Search (Looks near registration/fee keywords)
    pricing_list = []
    fee_contexts = soup.find_all(string=re.compile(r'fee|price|cost|delegate|registration|\$', re.I))
    for ctx in fee_contexts:
        parent_text = ctx.parent.get_text() if ctx.parent else ""
        prices = re.findall(r'(\$\d+(?:\.\d{2})?|\d+\s?CAD|\d+\s?USD|\d+\s?EUR|\d+\s?GBP)', parent_text)
        for p in prices:
            if p not in pricing_list:
                pricing_list.append(p)
    
    pricing_str = ", ".join(pricing_list[:5]) if pricing_list else "Check website for fee schedule."

    # 4. Committee Extraction (Scrapes tables, lists, and common MUN committees)
    committees = []
    
    # Check tables & structured blocks
    for element in soup.find_all(['td', 'h3', 'h4', 'a', 'li']):
        text = element.get_text().strip()
        # Look for committee names or acronyms
        if any(kw in text.upper() for kw in ["UNSC", "DISEC", "SOCHUM", "SPECPOL", "ECOSOC", "ICJ", "CRISIS", "PRESS", "WHO", "UNHRC", "HISTORICAL"]):
            if len(text) < 60 and text not in committees:
                committees.append(text)
        elif "committee" in text.lower() or "council" in text.lower():
            if 5 < len(text) < 50 and text not in committees:
                committees.append(text)

    committees_formatted = "\n• " + "\n• ".join(committees[:10]) if committees else "See website for committee matrix."

    return {
        "title": title,
        "url": url,
        "dates": dates,
        "pricing": pricing_str,
        "committees": committees_formatted,
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Flag_of_the_United_Nations.svg/1200px-Flag_of_the_United_Nations.svg.png"
    }

# ---------------------------------------------------------
# BOT COMMANDS
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
    await interaction.response.defer(thinking=True)
    
    # Fetch dynamic HTML using Playwright in an async task
    html_content = await fetch_rendered_html(url)
    
    # Run parsing in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, scrape_mun_website_smart, url, html_content)

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

if __name__ == "__main__":
    bot.run(BOT_TOKEN)