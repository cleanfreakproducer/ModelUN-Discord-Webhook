import os
import re
import json
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------
# GEMINI LIVE WEB SEARCH SCRAPER
# ---------------------------------------------------------
async def scrape_with_gemini(url: str) -> dict:
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY environment variable is not configured."}

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        Research and analyze the Model UN conference at this URL/organization: {url}
        Search the web and navigate its pages if needed to find exact, up-to-date conference details.
        
        Return ONLY a valid raw JSON object (no markdown formatting, no code blocks) with these exact keys:
        - "title": string (e.g. "CAIMUN")
        - "dates": string (e.g. "May 22-24, 2026")
        - "pricing": string (e.g. "$75 Delegate Fee, $45 Delegation Fee")
        - "committees": string (list up to 8 committees separated by bullet points e.g. "• UNSC\n• DISEC\n• SOCHUM")
        """

        # Using Flash-Lite with Google Search grounding enabled
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        raw_text = response.text.strip()
        # Clean any markdown code fences if generated
        clean_json = re.sub(r'```json|```', '', raw_text).strip()
        extracted = json.loads(clean_json)

        return {
            "title": extracted.get("title", "Model UN Conference"),
            "url": url,
            "dates": extracted.get("dates", "See website for dates"),
            "pricing": extracted.get("pricing", "See website for fees"),
            "committees": extracted.get("committees", "See website for committee list"),
            "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Flag_of_the_United_Nations.svg/1200px-Flag_of_the_United_Nations.svg.png"
        }

    except Exception as e:
        print(f"Gemini live search error: {e}")
        return {"error": f"Failed to retrieve conference details: {str(e)}"}

# ---------------------------------------------------------
# DISCORD BOT COMMANDS
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="mun", description="Scrape and package info for a Model UN conference")
@app_commands.describe(url="The URL of the MUN conference website")
async def mun_command(interaction: discord.Interaction, url: str):
    # Defer response immediately to prevent Discord's 3-second timeout
    await interaction.response.defer(thinking=True)
    
    data = await scrape_with_gemini(url)

    if "error" in data:
        await interaction.followup.send(f"❌ {data['error']}")
        return

    embed = discord.Embed(
        title=f"🇺🇳 {data['title']}",
        url=data['url'],
        description="Here are the conference details retrieved from the official website:",
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