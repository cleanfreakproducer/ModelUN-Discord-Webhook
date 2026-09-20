import os
import re
import json
import asyncio
import requests
from bs4 import BeautifulSoup
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from urllib.parse import urljoin, urlparse

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# AI-POWERED SCRAPER (NON-BLOCKING)
# ---------------------------------------------------------
async def scrape_with_gemini(url: str) -> dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 1. Fetch main page and subpages concurrently
    def fetch_site_content():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
        except Exception as e:
            return None, f"failed to reach website: {str(e)}"

        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "Model UN Conference"
        
        # Base page text
        combined_text = [soup.get_text(separator=' ')]
        
        # Discover relevant subpage links (e.g. /committees, /registration, /about)
        target_keywords = ["committee", "register", "registration", "fee", "about", "schedule"]
        base_domain = urlparse(url).netloc
        subpage_urls = set()

        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urljoin(url, href)
            # Ensure it's inside the same domain and matches key MUN subpages
            if urlparse(full_url).netloc == base_domain:
                if any(kw in href.lower() for kw in target_keywords):
                    subpage_urls.add(full_url)

        # Scrape up to 4 relevant subpages
        for sub_url in list(subpage_urls)[:4]:
            try:
                sub_res = requests.get(sub_url, headers=headers, timeout=5)
                if sub_res.status_code == 200:
                    sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
                    combined_text.append(sub_soup.get_text(separator=' '))
            except Exception:
                continue

        # Combine text and truncate to fit context window safely
        full_site_text = " ".join(combined_text)[:30000]
        return (title, full_site_text), None

    site_data, error = await asyncio.to_thread(fetch_site_content)
    
    if error:
        return {"error": error}
        
    title, page_text = site_data

    # 2. Asynchronous Gemini Call with combined text
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"""
            Extract Model UN conference details from the combined website text below.
            Return ONLY a valid JSON object with these keys:
            - "dates": string (e.g. "March 5-7, 2027")
            - "pricing": string (e.g. "$65 Delegate Fee, $40 Delegation Fee")
            - "committees": string (list up to 8 committees separated by bullet points e.g. "• UNSC\n• DISEC")

            Website Text:
            {page_text}
            """
            
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            clean_json = re.sub(r'```json|```', '', response.text).strip()
            extracted = json.loads(clean_json)

            return {
                "title": title,
                "url": url,
                "dates": extracted.get("dates", "See website"),
                "pricing": extracted.get("pricing", "See website"),
                "committees": extracted.get("committees", "See website"),
                "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Flag_of_the_United_Nations.svg/1200px-Flag_of_the_United_Nations.svg.png"
            }
        except Exception as e:
            print(f"gemini extraction warning: {e}")

    return {
        "title": title,
        "url": url,
        "dates": "Check website for dates",
        "pricing": "Refer to website for fees",
        "committees": "See website for full list",
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Flag_of_the_United_Nations.svg/1200px-Flag_of_the_United_Nations.svg.png"
    }

# ---------------------------------------------------------
# DISCORD BOT COMMANDS
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print(f"logged in as {bot.user}")
    await bot.tree.sync()

@bot.tree.command(name="mun", description="scrape and package info for a model un conference website")
@app_commands.describe(url="the url of the mun conference website")
async def mun_command(interaction: discord.Interaction, url: str):
    # defer immediately so discord gives the bot up to 15 minutes to respond
    await interaction.response.defer(thinking=True)
    
    # scrape asynchronously
    data = await scrape_with_gemini(url)

    if "error" in data:
        await interaction.followup.send(f"❌ {data['error']}")
        return

    embed = discord.Embed(
        title=f"🇺🇳 {data['title']}",
        url=data['url'],
        description="here are the conference details retrieved from the official website:",
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