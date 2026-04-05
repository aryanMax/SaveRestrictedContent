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
            await conv.send_message(f"✅ Selected: **{selected_channel.name}
