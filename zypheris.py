import os
import json
from collections import deque
import discord
from discord.ext import commands
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TRIGGER = "zypheris"
MEMORY_LIMIT = 200
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")
PARENT_MEMORY_FILE = os.path.join(os.path.dirname(BASE_DIR), "memory.json")
OWNER_NAME = os.getenv("OWNER_NAME", "my owner")

SYSTEM_PROMPT = (
    "You are Zypheris, an intelligent, helpful, and friendly Discord assistant powered by Gemini. "
    "You provide clear, accurate, and insightful answers just like Gemini, while matching the tone of the conversation. "
    f"Your creator and owner is {OWNER_NAME}; respect them and mention them proudly if asked. "
    "You have a persistent memory of your past conversations with users in this channel — use it to maintain context."
)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-3.6-flash",
    system_instruction=SYSTEM_PROMPT
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

memory: dict[int, deque] = {}


def load_memory():
    global memory
    target_file = MEMORY_FILE if os.path.exists(MEMORY_FILE) else (PARENT_MEMORY_FILE if os.path.exists(PARENT_MEMORY_FILE) else None)
    if not target_file:
        return
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for cid, entries in raw.items():
            memory[int(cid)] = deque(entries, maxlen=MEMORY_LIMIT)
        print(f"Loaded memory for {len(memory)} channel(s) from {target_file}.")
    except Exception as e:
        print(f"Failed to load memory: {e}")


def save_memory():
    try:
        raw = {str(cid): list(dq) for cid, dq in memory.items()}
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save memory: {e}")


def get_history(channel_id: int) -> deque:
    if channel_id not in memory:
        memory[channel_id] = deque(maxlen=MEMORY_LIMIT)
    return memory[channel_id]


def to_gemini_history(entries) -> list:
    history = []
    expected_role = "user"
    for e in entries:
        role = e.get("role")
        text = e.get("text", "")
        if not text:
            continue
        # Gemini history must start with "user" and alternate between "user" and "model"
        if role == expected_role:
            history.append({
                "role": role,
                "parts": [text]
            })
            expected_role = "model" if expected_role == "user" else "user"
        elif history and role == history[-1]["role"]:
            # Combine text if consecutive same roles
            history[-1]["parts"].append(text)

    # If the last item in history is a user message, drop it so Gemini starts cleanly
    if history and history[-1]["role"] == "user":
        history.pop()

    return history


def extract_prompt(content: str) -> str:
    lower = content.lower()
    idx = lower.find(TRIGGER)
    if idx == -1:
        return ""
    cleaned = content[:idx] + content[idx + len(TRIGGER):]
    return cleaned.strip(" ,.!?\n\t")


@bot.event
async def on_ready():
    load_memory()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Zypheris is online. Trigger word: {TRIGGER}")
    print("------")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if TRIGGER not in message.content.lower():
        return

    prompt = extract_prompt(message.content)

    if not prompt:
        prompt = "Hello! Say hi back to the user in a friendly way."

    channel_id = message.channel.id
    history = get_history(channel_id)

    async with message.channel.typing():
        try:
            # 1. Prepare chat session with sanitized history
            formatted_history = to_gemini_history(history)
            chat = model.start_chat(history=formatted_history)

            # 2. Call Gemini asynchronously to avoid blocking Discord bot
            response = await chat.send_message_async(prompt)
            reply_text = response.text.strip() if response.text else "I couldn't generate a response."

            # 3. Save exchange in memory
            history.append({"role": "user", "text": prompt})
            history.append({"role": "model", "text": reply_text})
            save_memory()

            # 4. Handle Discord's 2000 character limit
            if len(reply_text) <= 2000:
                await message.reply(reply_text, mention_author=False)
            else:
                chunks = [reply_text[i:i + 1900] for i in range(0, len(reply_text), 1900)]
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        await message.reply(chunk, mention_author=False)
                    else:
                        await message.channel.send(chunk)

        except Exception as e:
            print(f"Gemini API Error: {e}")
            await message.reply(f"⚠️ **Error connecting to Gemini:**\n`{e}`", mention_author=False)

    await bot.process_commands(message)


@bot.event
async def on_disconnect():
    save_memory()


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)