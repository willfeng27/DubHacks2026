import discord
import asyncio
import random
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai
from google.genai import types

# --- CONFIGURATION ---
GEMINI_API_KEY = "AQ.Ab8RN6JWF_IZ-e0uMrFtpQwaSj9VU3HbgypN7Io1LtkprcwXww"
DISCORD_BOT_TOKEN = "MTU2MTEwOTA2MzgyMTk1OTM3OQ.G9hExF.SQHvf0f_32VGFW71LoParaZy5XixTyWQ_CCHm4"
REPORT_EMAIL = "carsonschiller@comcast.net"

# SMTP Settings for sending reports (Ensure SENDER_PASSWORD is a 16-character Gmail App Password)
SMTP_SERVER = "smtp.comcast.net"
SMTP_PORT = 465
SENDER_EMAIL = "carsonschiller@comcast.net"
SENDER_PASSWORD = "eiffel3993"
# ---------------------

# Initialize Gemini Client safely
try:
    client_gemini = genai.Client(api_key=GEMINI_API_KEY)
except Exception as init_e:
    print(f"Failed to initialize Gemini Client: {init_e}")

intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

# Dictionary to manage unique session state per user ID
user_sessions = {}

SYSTEM_PROMPT = (
    "You are a millennial online buyer who wants whatever item or offer is being discussed, "
    "but you only have 60% of the requested funds. You are slightly skeptical occasionally, "
    "but discreetly so as to not scare them off. Ask for payment details (email, Zelle, CashApp, PayPal, wire) "
    "only deeper into the conversation to play the long game. Keep responses somewhat short, mostly lowercase, "
    "and include minor spelling typos or lack of punctuation every few messages."
)

# Regex Patterns for Data Extraction
PATTERNS = {
    "Email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "Crypto Wallet": r'\b(0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{39,59})\b',
    "Routing/Account/Phone": r'\b\d{9,12}\b'
}

def extract_information(text):
    found = []
    for label, pattern in PATTERNS.items():
        matches = re.findall(pattern, text)
        for match in matches:
            found.append(f"{label}: {match}")
    return found

def send_email_report(user_id, username, history_log, collected_info):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = REPORT_EMAIL
        msg['Subject'] = f"[Scam-Bait Summary] Transcript for User: {username} ({user_id})"

        formatted_history = "\n".join(history_log)
        formatted_data = "\n".join(collected_info) if collected_info else "None detected."

        body = (
            f"=== SCAM-BAIT BOT SESSION REPORT ===\n"
            f"Target User: {username}\n"
            f"User ID: {user_id}\n\n"
            f"--- EXTRACTED DATA ---\n"
            f"{formatted_data}\n\n"
            f"--- FULL CHAT TRANSCRIPT ---\n"
            f"{formatted_history}\n"
        )

        msg.attach(MIMEText(body, 'plain'))

        # Standard TLS connection
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Summary report successfully emailed for user {user_id}.")
    except Exception as e:
        print(f"Failed to send email report via TLS: {e}")
        # Secondary fallback via SSL port 465
        try:
            print("Attempting fallback via SSL (port 465)...")
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("Fallback email report sent successfully via SSL.")
        except Exception as fallback_e:
            print(f"Fallback email dispatch also failed: {fallback_e}")

@bot.event
async def on_ready():
    print(f"Bot active as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Restrict processing to Direct Messages only
    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        username = str(message.author)
        user_text = message.content

        # Create unique Gemini chat session per user
        if user_id not in user_sessions:
            try:
                chat = client_gemini.chats.create(
                    model="gemini-3.7-flash",  # Active model with fresh quota
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.7
                    )
                )
                user_sessions[user_id] = {
                    "chat_session": chat,
                    "collected_data": set(),
                    "history_log": []
                }
            except Exception as chat_e:
                print(f"Error creating Gemini chat session: {chat_e}")
                return

        session = user_sessions[user_id]

        # Scan text for payment data
        extracted = extract_information(user_text)
        for item in extracted:
            session["collected_data"].add(item)

        session["history_log"].append(f"USER: {user_text}")

        # Manual session close and report command
        if user_text.lower().strip() == "!end_session":
            send_email_report(user_id, username, session["history_log"], session["collected_data"])
            await message.channel.send("Session closed and report dispatched.")
            return

        # Randomized delay (set to 5s for testing, change back to random.randint(20, 600) later)
        delay = 5
        print(f"DM from {username}. Replying in {delay} seconds...")

        async with message.channel.typing():
            await asyncio.sleep(delay)

            try:
                # Offload blocking network request to a background thread to prevent heartbeat freezes
                response = await asyncio.to_thread(session["chat_session"].send_message, user_text)
                reply_text = response.text

                session["history_log"].append(f"BOT: {reply_text}")
                await message.channel.send(reply_text)

            except Exception as e:
                print(f"Error during Gemini API call: {e}")

try:
    bot.run(DISCORD_BOT_TOKEN)
except Exception as run_e:
    print(f"Bot failed to start: {run_e}")
