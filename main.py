import os
import time
import asyncio
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# --- Flask Server for Koyeb Health Checks ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive and running!", 200

def run_flask():
    # Koyeb passes the port via environment variable, defaults to 8000
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

# --- User Credentials ---
API_ID = 12155241
API_HASH = '5d4fb21990c47b88df74dc1611a07483'
STRING_SESSION = '1AZWarzYBu5ylu1u3Ra81TEtn3h6b5Z2VebwueLMh8Ay-kSXrZHKAZ-HJDCvourbbbiu1UZvOvUp4jK5TrjEXZr1-zKKG6T_xMQLA_fi7BzXOegB_ib7evsw7qeJvpoHjXFV7HFHrNENGppXxSY_QvJk0swDVrcwTqREsjSsrXV7fWkLaoHbzPAWBbM_aEoOXk7pA3H4gCWoyeBDllLrbFpGSF6ZH1Y0ZS9qFDz32Rn-BRjAnPZWo72BK2bBJz4UF5UbXpjr6igLDytrmATPPFDfdlsAnTTs4rYqpGM0hBKatAFxEEt1WmEsWVdfh27eo-AckQLbJl2-fIvyXdwYhSTEs62tMevQ='
BOT_TOKEN = '8498132641:AAE-SV9DyRcn30SnTxC5CBjHc2F9XxswTag'

# --- Client Initialization ---
bot = TelegramClient('bot_session', API_ID, API_HASH)
user = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

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

# --- Bot Commands ---
@bot.on(events.NewMessage(pattern='/start'))
async def handler(event):
    chat_id = event.chat_id
    async with bot.conversation(chat_id) as conv:
        try:
            await conv.send_message("🛠 **Select Mode:**\nReply `1` for Entire Channel\nReply `2` for Single Message ID")
            mode = (await conv.get_response()).text.strip()
            await conv.send_message("📂 **Source:** Enter Source Channel ID (e.g., -100123456789):")
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
        except Exception as e: await bot.send_message(chat_id, f"⚠️ Error: {e}")

# --- Runner with Startup Protection ---
async def start_services():
    threading.Thread(target=run_flask, daemon=True).start()
    print("Health check server started on port 8000.")

    while True:
        try:
            print("Attempting to start Bot Client...")
            await bot.start(bot_token=BOT_TOKEN); break
        except FloodWaitError as e:
            print(f"⚠️ Startup FloodWait: Waiting {e.seconds}s. DO NOT RESTART."); await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print(f"❌ Error: {e}"); await asyncio.sleep(30)

    while True:
        try:
            print("Attempting to start User Client...")
            await user.start(); break
        except FloodWaitError as e:
            print(f"⚠️ User Client FloodWait: Waiting {e.seconds}s."); await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print(f"❌ Error: {e}"); await asyncio.sleep(30)

    print("✅ All systems go!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try: asyncio.run(start_services())
    except KeyboardInterrupt: pass
