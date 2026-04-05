import os
import time
import asyncio
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SessionPasswordNeededError

# --- Flask Server for Koyeb Health Checks ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive and running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

# --- User Credentials ---
API_ID = 12155241
API_HASH = '5d4fb21990c47b88df74dc1611a07483'
BOT_TOKEN = '8498132641:AAE-SV9DyRcn30SnTxC5CBjHc2F9XxswTag'

# You can paste your string session here later to skip the /login step on future restarts
STRING_SESSION = '' 

# --- Client Initialization ---
bot = TelegramClient('bot_session', API_ID, API_HASH)
user = None # User client is initialized later

# --- Helpers ---
def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

async def progress_bar(current, total, msg, action, start_time, last_update):
    now = time.time()
    if (now - last_update[0]) < 5 and current < total:
        return
    last_update[0] = now
    elapsed = max(1, round(now - start_time))
    speed = current / elapsed
    percentage = (current / total) * 100
    bar = '█' * int(percentage / 10) + '░' * (10 - int(percentage / 10))
    status_text = (f"**{action}**\n`{bar}` {percentage:.1f}%\n"
                   f"🚀 Speed: {format_bytes(speed)}/s\n"
                   f"📦 Processed: {format_bytes(current)} / {format_bytes(total)}")
    try: await msg.edit(status_text)
    except: pass

# --- In-Chat Login Command ---
@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    global user
    chat_id = event.chat_id
    
    async with bot.conversation(chat_id) as conv:
        try:
            await conv.send_message("📱 **Step 1:** Enter your phone number with country code (e.g., +919876543210):")
            phone = (await conv.get_response()).text.strip()
            
            # Initialize temp user client
            user = TelegramClient(StringSession(), API_ID, API_HASH)
            await user.connect()
            
            await user.send_code_request(phone)
            
            await conv.send_message("✉️ **Step 2:** Enter the 5-digit code Telegram just sent you.\n\n⚠️ **CRITICAL:** You MUST send it with spaces or dashes (e.g., `1 2 3 4 5`). If you send it normally, Telegram will instantly expire it!")
            raw_code = (await conv.get_response()).text
            # Clean the code to remove spaces and dashes
            clean_code = raw_code.replace(' ', '').replace('-', '').strip()
            
            try:
                await user.sign_in(phone, clean_code)
            except SessionPasswordNeededError:
                await conv.send_message("🔒 **Step 3:** Two-Step Verification Detected. Enter your password:")
                pwd = (await conv.get_response()).text.strip()
                await user.sign_in(password=pwd)
            
            new_string = user.session.save()
            success_msg = (
                "✅ **Login Successful! User Client is now ACTIVE.**\n\n"
                "**IMPORTANT:** Here is your permanent String Session:\n\n"
                f"`{new_string}`\n\n"
                "Save this string! Add it to your `main.py` code later so you don't have to log in every time Koyeb restarts. "
                "For now, you can immediately send `/start` to begin copying files!"
            )
            await conv.send_message(success_msg)
            
        except Exception as e:
            await conv.send_message(f"❌ **Login Failed:** {e}\nSend `/login` to try again.")
            user = None

# --- Main Forwarding Command ---
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    global user
    chat_id = event.chat_id
    
    if user is None or not await user.is_user_authorized():
        await bot.send_message(chat_id, "⚠️ **User Client is not logged in!**\nPlease send `/login` first to authenticate your account.")
        return

    async with bot.conversation(chat_id) as conv:
        try:
            await conv.send_message("🛠 **Select Mode:**\nReply `1` for Entire Channel\nReply `2` for Single Message ID")
            mode = (await conv.get_response()).text.strip()
            
            await conv.send_message("📂 **Source:** Enter Source Channel ID (must start with -100):")
            src_id = int((await conv.get_response()).text.strip())
            
            await conv.send_message("🎯 **Destination:** Enter Destination Channel ID:")
            dst_id = int((await conv.get_response()).text.strip())

            source_entity = await user.get_entity(src_id)
            is_restricted = getattr(source_entity, 'noforwards', False)
            
            messages_to_copy = []
            if mode == '1':
                await conv.send_message("🔍 Scanning channel for media...")
                async for m in user.iter_messages(src_id, reverse=True):
                    if m.media: messages_to_copy.append(m)
            else:
                await conv.send_message("🆔 Enter the Message ID:")
                m_id = int((await conv.get_response()).text.strip())
                m = await user.get_messages(src_id, ids=m_id)
                if m and m.media: messages_to_copy.append(m)

            if not messages_to_copy:
                await conv.send_message("❌ No media found."); return

            await conv.send_message(f"✅ Found {len(messages_to_copy)} files. Starting transfer...")

            for i, m in enumerate(messages_to_copy, 1):
                status_msg = await bot.send_message(chat_id, f"Processing file {i}/{len(messages_to_copy)}...")
                try:
                    if is_restricted:
                        start_time = time.time(); last_upd = [start_time]
                        path = await user.download_media(m, progress_callback=lambda c, t: progress_bar(c, t, status_msg, f"Downloading {i}", start_time, last_upd))
                        start_time = time.time(); last_upd = [start_time]
                        await user.send_file(dst_id, path, caption=m.text, progress_callback=lambda c, t: progress_bar(c, t, status_msg, f"Uploading {i}", start_time, last_upd))
                        if os.path.exists(path): os.remove(path)
                    else:
                        await user.forward_messages(dst_id, m)
                    await status_msg.edit(f"✅ File {i} transferred."); await asyncio.sleep(2)
                except FloodWaitError as e:
                    await bot.send_message(chat_id, f"⚠️ Rate Limit! Sleeping {e.seconds}s..."); await asyncio.sleep(e.seconds)
                except Exception as e:
                    await bot.send_message(chat_id, f"❌ Error: {e}")
            await bot.send_message(chat_id, "🏁 **Transfer Complete!**")
        except Exception as e:
            await bot.send_message(chat_id, f"⚠️ Error: {e}")

# --- Background Services ---
async def start_services():
    global user
    # Start Health Check
    threading.Thread(target=run_flask, daemon=True).start()
    print("✅ Health check server live on port 8000.")

    # Start Bot Client
    print("Attempting to start Bot Client...")
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot Client is Online.")

    # Check if a String Session was hardcoded
    if STRING_SESSION:
        try:
            print("String Session found, attempting to connect User Client...")
            user = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
            await user.connect()
            if await user.is_user_authorized():
                print("✅ User Client is Online via hardcoded string.")
        except Exception as e:
            print(f"⚠️ Hardcoded String Session failed: {e}")

    print("🚀 Bot is ready. Send /login or /start on Telegram.")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try: asyncio.run(start_services())
    except KeyboardInterrupt: pass
