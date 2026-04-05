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

# --- Credentials ---
API_ID = 12155241
API_HASH = '5d4fb21990c47b88df74dc1611a07483'
BOT_TOKEN = '8498132641:AAE-SV9DyRcn30SnTxC5CBjHc2F9XxswTag'

# Your updated, authorized String Session
STRING_SESSION = '1AZWarzkBuwgN4VaU0uTtr1QyMzMcR7g7aPuFeQscmSpdYw7Iquk3_JI1XxE4eUzHRGnOXhAW8tMLzNfVu8eLB7yLqjs69bWP6ML3pvQpjrQOi9aIMs39WAhfFEPrkMIyvI_JAtD4-zrjWVlh9KqmnWX4XXfhpz2276mJWW8cevVhkKBSnv3YXgVjAjNliS3zy1TTQO08wXw-efD0iMHyxo6Q9fvp1kEeUOPBqfLbRIfxKIgQjHCUANR46aepz9hm_Sq7j6VIu8wqM_jlbXA7z0upsswXyiKY3gA8HtSXxdXlrMKh9sv6u9xUSZILFAD9uAgN-fByvPR71lTuvwqdgRTQH2LOzHg='

# --- Client Initialization ---
bot = TelegramClient('bot_session', API_ID, API_HASH)
user = None 

# --- Helpers ---
def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

def parse_message_id(input_text):
    """Extracts the message ID whether it's a raw number or a Telegram link."""
    text = input_text.strip()
    if '/' in text:
        text = text.split('/')[-1] # Gets the last part of the URL
    if '?' in text:
        text = text.split('?')[0]  # Removes things like '?single'
    return int(text)

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

async def select_channel(conv, prompt_title):
    """Helper function to let users search for channels by name or ID"""
    prompt = (f"{prompt_title}\n"
              "Type a part of the channel's name to search your joined groups.\n"
              "*(Alternatively, just paste the raw `-100` ID)*")
    await conv.send_message(prompt)
    
    search_term = (await conv.get_response()).text.strip()
    
    # If the user just pastes the ID directly, bypass the search
    if search_term.lstrip('-').isdigit():
        return int(search_term)
        
    await conv.send_message("🔍 Searching your channels...")
    
    # Fetch up to 200 recent dialogs to find matches
    dialogs = await user.get_dialogs(limit=200)
    channels = [d for d in dialogs if d.is_channel or d.is_group]
    
    # Filter by search term
    matches = [c for c in channels if search_term.lower() in c.name.lower()]
    
    if not matches:
        await conv.send_message("❌ No channels found matching that name. Please start over with `/start`.")
        return None
        
    matches = matches[:40] # Limit to 40 to fit in a single Telegram message
    
    msg_text = "🎯 **Found these matching channels:**\n\n"
    for i, c in enumerate(matches, 1):
        msg_text += f"**{i}.** {c.name}\n"
        
    msg_text += "\nReply with the **Number** of the channel you want to select:"
    await conv.send_message(msg_text)
    
    choice = (await conv.get_response()).text.strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            selected_channel = matches[idx]
            await conv.send_message(f"✅ Selected: **{selected_channel.name}** (`{selected_channel.id}`)")
            return selected_channel.id
        else:
            await conv.send_message("❌ Invalid number. Please start over with `/start`.")
            return None
    except ValueError:
        await conv.send_message("❌ Invalid input. Please start over with `/start`.")
        return None

# --- Main Forwarding Command ---
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    global user
    chat_id = event.chat_id
    
    if user is None or not await user.is_user_authorized():
        await bot.send_message(chat_id, "⚠️ **User Client is not logged in!**\nCheck Koyeb logs or String Session.")
        return

    # Timeout increased to 300 seconds (5 minutes)
    async with bot.conversation(chat_id, timeout=300) as conv:
        try:
            # 1. Source Channel
            src_id = await select_channel(conv, "📂 **SOURCE CHANNEL**")
            if not src_id: return
            
            # 2. Destination Channel
            dst_id = await select_channel(conv, "🎯 **DESTINATION CHANNEL**")
            if not dst_id: return

            # 3. Select Copy Mode
            mode_prompt = (
                "🛠 **Select Copy Mode:**\n"
                "`1` - Copy **Entire** Channel\n"
                "`2` - Copy a **Single** Message\n"
                "`3` - Copy a specific Message **AND all messages below it**"
            )
            await conv.send_message(mode_prompt)
            mode = (await conv.get_response()).text.strip()

            source_entity = await user.get_entity(src_id)
            is_restricted = getattr(source_entity, 'noforwards', False)
            
            messages_to_copy = []
            
            if mode == '1':
                await conv.send_message("🔍 Scanning entire channel for media...")
                async for m in user.iter_messages(src_id, reverse=True):
                    if m.media: messages_to_copy.append(m)
                    
            elif mode == '2':
                await conv.send_message("🆔 Enter the exact **Message ID** or **Message Link**:")
                m_input = (await conv.get_response()).text.strip()
                m_id = parse_message_id(m_input)
                
                m = await user.get_messages(src_id, ids=m_id)
                if m and m.media: messages_to_copy.append(m)
                
            elif mode == '3':
                await conv.send_message("🆔 Enter the STARTING **Message ID** or **Message Link**:\n*(This message and everything posted after it will be copied)*")
                m_input = (await conv.get_response()).text.strip()
                m_id = parse_message_id(m_input)
                
                await conv.send_message("🔍 Scanning channel downwards from that message...")
                # min_id=m_id-1 grabs the message itself and all newer messages
                async for m in user.iter_messages(src_id, reverse=True, min_id=m_id - 1):
                    if m.media: messages_to_copy.append(m)

            if not messages_to_copy:
                await conv.send_message("❌ No media found in that range."); return

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
                    await bot.send_message(chat_id, f"❌ Error on file {i}: {e}")
            
            await bot.send_message(chat_id, "🏁 **Transfer Complete!**")
        
        except asyncio.TimeoutError:
            await conv.send_message("⏳ **Conversation timed out (5 minutes passed).** Please type `/start` again when you are ready.")
        except Exception as e:
            await bot.send_message(chat_id, f"⚠️ **An error occurred:** {e}")

# --- Background Services ---
async def start_services():
    global user
    
    threading.Thread(target=run_flask, daemon=True).start()
    print("✅ Health check server live on port 8000.")

    print("Attempting to start Bot Client...")
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot Client is Online.")

    while True:
        try:
            print("Attempting to connect User Client via String Session...")
            user = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
            await user.connect()
            
            if await user.is_user_authorized():
                print("✅ User Client (Worker) is Online and Authorized.")
                break
            else:
                print("❌ CRITICAL: The String Session is invalid or expired. Cannot authorize.")
                break
                
        except FloodWaitError as e:
            print(f"⚠️ Telegram FloodWait: Waiting {e.seconds}s. DO NOT RESTART.")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print(f"❌ USER SESSION ERROR: {e}")
            await asyncio.sleep(
