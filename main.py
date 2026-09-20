import os
import re
import json
import requests
from bs4 import BeautifulSoup
import discord
from discord import app_commands
from discord.ext import commands
from google import genai

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# AI-POWERED SCRAPER
# ---------------------------------------------------------
def scrape_with_gemini(url: str) -> dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=12)
        res.raise_for_status()
    except Exception as e:
        return {"error": f"Failed to reach website: {str(e)}"}

    soup = BeautifulSoup(res.text, 'html.parser')
    page_text = soup.get_text(separator=' ')[:15000] # Pass first 15k characters
    title = soup.title.string.strip() if soup.title else "Model UN Conference"

    # Call Gemini to extract structured info
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"""
            Extract Model UN conference details from the text below. 
            Return ONLY a valid JSON object with these keys:
            - "dates": string (e.g. "May 15-17, 2026")
            - "pricing": string (e.g. "$65 Delegate Fee, $40 Delegation Fee")
            - "committees": string (list up to 8 committees separated by bullet points e.g. "• UNSC\n• DISEC")

            Website Text:
            {page_text}
            """
            response = client.models.generate_content(
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
            print(f"Gemini extraction warning: {e}")

    # Fallback if Gemini API key isn't provided or fails
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
    await interaction.response.defer(thinking=True)
    
    data = scrape_with_gemini(url)

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