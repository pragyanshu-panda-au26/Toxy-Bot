# Toxy-Bot
# Discord Anti-Raid & Anti-Nuke Bot

A powerful Discord bot with anti-raid, anti-nuke protection, and custom commands functionality.

## Features

### 🛡️ Anti-Nuke Protection
- **Channel Deletion Protection**: Automatically bans any admin who deletes 2 or more channels within 60 seconds
- **Audit Log Monitoring**: Tracks channel deletions through Discord's audit logs
- **Automatic Banning**: Instantly bans offending administrators

### 🚨 Anti-Raid Protection
- **Rapid Join Detection**: Monitors member joins and detects potential raids (5+ joins in 10 seconds)
- **Mass Mention Protection**: Prevents mass mentions (5+ users in one message)
- **Spam Detection**: Detects and removes repeated spam messages

### ⚙️ Custom Commands
- Add, delete, and list custom commands
- Commands are saved persistently in `custom_commands.json`
- Easy-to-use command system

### 🌅 Morning Messages
- **Automatic Daily Messages**: Sends a morning message with @everyone mention at 8:00 AM daily
- **Custom Messages**: Set custom morning messages per server
- **Channel Configuration**: Choose which channel receives morning messages
- **Test Command**: Test morning messages before the scheduled time

## Quick Deploy

**For cloud deployment (Railway, Heroku, etc.):**
1. Set `DISCORD_BOT_TOKEN` environment variable
2. Deploy - platform will auto-detect and run
3. See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Your Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Enable the following Privileged Gateway Intents:
   - MESSAGE CONTENT INTENT
   - SERVER MEMBERS INTENT

### 3. Invite Bot to Your Server

Use this URL (replace CLIENT_ID with your bot's client ID):
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot
```

Or use minimal permissions:
- Manage Messages
- Ban Members
- View Audit Logs
- Send Messages
- Manage Channels (for protection)

### 4. Set Your Bot Token

**Option 1: Environment Variable**
```bash
# Windows PowerShell
$env:DISCORD_BOT_TOKEN="your_token_here"

# Windows CMD
set DISCORD_BOT_TOKEN=your_token_here

# Linux/Mac
export DISCORD_BOT_TOKEN="your_token_here"
```

**Option 2: .env File**
Create a `.env` file:
```
DISCORD_BOT_TOKEN=your_token_here
```

**Option 3: Enter when prompted**
The bot will ask for the token if not found in environment variables.

### 5. Run the Bot

```bash
python bot.py
```

## Commands

### Custom Commands
- `!addcmd <name> <response>` - Add a custom command (Admin only)
- `!delcmd <name>` - Delete a custom command (Admin only)
- `!listcmd` - List all custom commands

### Morning Message Commands
- `!setmorning [channel]` - Set the channel for morning messages (Admin only, defaults to current channel)
- `!removemorning` - Remove morning messages for this server (Admin only)
- `!setmorningmsg <message>` - Set a custom morning message (Admin only)
- `!morninginfo` - Check morning message settings
- `!testmorning` - Test the morning message (Admin only)

### Utility Commands
- `!ping` - Check bot latency
- `!info` - Show bot information
- `!clear [amount]` - Clear messages (Mod only, default: 10, max: 100)

## Protection Features

### Anti-Nuke
- Monitors all channel deletions
- If an admin deletes 2+ channels within 60 seconds, they are automatically banned
- Sends alerts to `mod-log` or `logs` channel if available

### Anti-Raid
- Tracks member joins (alerts if 5+ join in 10 seconds)
- Blocks mass mentions (5+ users)
- Detects spam (same message 5+ times)
- Automatically times out spammers for 10 minutes

## Configuration

The bot uses a default prefix of `!`. To change it, modify the `command_prefix` in `bot.py`:

```python
bot = commands.Bot(command_prefix='!', intents=intents)
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

**Quick Deploy Options:**
- **Railway**: Connect GitHub repo → Add `DISCORD_BOT_TOKEN` → Deploy
- **Heroku**: `heroku create` → `heroku config:set DISCORD_BOT_TOKEN=...` → `git push heroku main`
- **Docker**: `docker build -t discord-bot .` → `docker run -e DISCORD_BOT_TOKEN=... discord-bot`
- **VPS**: See DEPLOYMENT.md for systemd service setup

## Files

- `bot.py` - Main bot file
- `Procfile` - Process definition for Heroku/Railway
- `runtime.txt` - Python version specification
- `Dockerfile` - Docker container configuration
- `requirements.txt` - Python dependencies
- `.env.example` - Example environment variables
- `custom_commands.json` - Stores custom commands (auto-generated)
- `morning_settings.json` - Stores morning message settings (auto-generated)
- `DEPLOYMENT.md` - Detailed deployment guide
- `README.md` - This file

## Important Notes

⚠️ **Make sure your bot has the following permissions:**
- Ban Members
- Manage Messages
- View Audit Logs
- Send Messages
- Manage Channels
- Timeout Members
- Mention Everyone (for morning messages)

⚠️ **The bot needs to be higher in the role hierarchy than users it needs to ban/timeout.**

## Troubleshooting

**Bot doesn't respond:**
- Check if the bot is online
- Verify the bot has "Send Messages" permission
- Check if MESSAGE CONTENT INTENT is enabled

**Anti-nuke not working:**
- Ensure the bot has "View Audit Logs" permission
- Bot must be higher in role hierarchy than admins

**Custom commands not saving:**
- Check file permissions in the bot's directory
- Ensure `custom_commands.json` is writable

## License

Free to use and modify for your own servers.

