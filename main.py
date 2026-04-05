from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
import asyncio
import time
import os

# --- Your Credentials ---
API_ID = 12155241
API_HASH = '5d4fb21990c47b88df74dc1611a07483'
STRING_SESSION = '1AZWarzYBu5ylu1u3Ra81TEtn3h6b5Z2VebwueLMh8Ay-kSXrZHKAZ-HJDCvourbbbiu1UZvOvUp4jK5TrjEXZr1-zKKG6T_xMQLA_fi7BzXOegB_ib7evsw7qeJvpoHjXFV7HFHrNENGppXxSY_QvJk0swDVrcwTqREsjSsrXV7fWkLaoHbzPAWBbM_aEoOXk7pA3H4gCWoyeBDllLrbFpGSF6ZH1Y0ZS9qFDz32Rn-BRjAnPZWo72BK2bBJz4UF5UbXpjr6igLDytrmATPPFDfdlsAnTTs4rYqpGM0hBKatAFxEEt1WmEsWVdfh27eo-AckQLbJl2-fIvyXdwYhSTEs62tMevQ='
BOT_TOKEN = '8498132641:AAE-SV9DyRcn30SnTxC5CBjHc2F9XxswTag'

# --- Initialization ---
bot = TelegramClient('bot_session', API_ID, API_HASH)
user = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

async def progress_bar(current, total, msg, action, start_time, last_update):
    now = time.time()
    if (now - last_update[0]) < 4 and current < total:
        return
    last_update[0] = now
    
    elapsed = max(1, round(now - start_time))
    speed = current / elapsed
    percentage = (current / total) * 100
    bar = '█' * int(percentage / 10) + '░' * (10 - int(percentage / 10))
    
    status_text = (f"**{action}**\n`{bar}` {percentage:.1f}%\n"
                   f"🚀 Speed: {format_bytes(speed)}/s\n"
                   f"📦 Done: {format_bytes(current)} / {format_bytes(total)}")
    try:
        await msg.edit(status_text)
    except:
        pass

@bot.on(events.NewMessage(pattern='/start'))
async def handler(event):
    async with bot.conversation(event.chat_id) as conv:
        await conv.send_message("📌 **Step 1:** Copy entire channel or specific files?\nReply `1` for All, `2` for Single ID.")
        mode = (await conv.get_response()).text
        
        await conv.send_message("📌 **Step 2:** Enter Source Channel ID (include -100):")
        src = int((await conv.get_response()).text)
        
        await conv.send_message("📌 **Step 3:** Enter Destination Channel ID (include -100):")
        dst = int((await conv.get_response()).text)

        source_entity = await user.get_entity(src)
        restricted = getattr(source_entity, 'noforwards', False)
        
        msgs = []
        if mode == '1':
            async for m in user.iter_messages(src, reverse=True):
                if m.media: msgs.append(m)
        else:
            await conv.send_message("Enter Message ID:")
            m_id = int((await conv.get_response()).text)
            m = await user.get_messages(src, ids=m_id)
            if m and m.media: msgs.append(m)

        await conv.send_message(f"✅ Found {len(msgs)} files. Starting transfer...")

        for i, m in enumerate(msgs, 1):
            status = await bot.send_message(event.chat_id, f"Processing {i}/{len(msgs)}...")
            try:
                if restricted:
                    # Download -> Upload (Preserves Thumbnails/Formats)
                    start = time.time()
                    last = [start]
                    path = await user.download_media(m, progress_callback=lambda c, t: progress_bar(c, t, status, "Downloading", start, last))
                    
                    start = time.time()
                    last = [start]
                    await user.send_file(dst, path, caption=m.text, thumb=path if path.endswith(('.jpg', '.png')) else None, 
                                        progress_callback=lambda c, t: progress_bar(c, t, status, "Uploading", start, last))
                    if os.path.exists(path): os.remove(path)
                else:
                    await user.forward_messages(dst, m)
                
                await status.edit(f"✅ Completed file {i}")
                await asyncio.sleep(2)
            except FloodWaitError as e:
                await bot.send_message(event.chat_id, f"⚠️ Rate limit! Sleeping {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                await bot.send_message(event.chat_id, f"❌ Error: {e}")

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    await user.start()
    print("Bot is live on Koyeb!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
