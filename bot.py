import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import json
import os
import webserver
import aiohttp

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Data storage
channel_deletion_times = defaultdict(list)  # {user_id: [timestamps]}
member_joins = defaultdict(list)  # {guild_id: [timestamps]}
custom_commands = {}  # {command_name: response}
morning_channels = {}  # {guild_id: channel_id}
morning_messages = {}  # {guild_id: custom_message}

# Load custom commands from file
COMMANDS_FILE = 'custom_commands.json'
MORNING_FILE = 'morning_settings.json'

def load_commands():
    global custom_commands
    if os.path.exists(COMMANDS_FILE):
        with open(COMMANDS_FILE, 'r') as f:
            custom_commands = json.load(f)

def save_commands():
    with open(COMMANDS_FILE, 'w') as f:
        json.dump(custom_commands, f, indent=4)

def load_morning_settings():
    global morning_channels, morning_messages
    if os.path.exists(MORNING_FILE):
        with open(MORNING_FILE, 'r') as f:
            data = json.load(f)
            morning_channels = data.get('channels', {})
            morning_messages = data.get('messages', {})

def save_morning_settings():
    with open(MORNING_FILE, 'w') as f:
        json.dump({
            'channels': morning_channels,
            'messages': morning_messages
        }, f, indent=4)

load_commands()
load_morning_settings()

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    await bot.change_presence(activity=discord.Game(name="Protecting your server!"))
    # Start the morning message task
    if not morning_message_task.is_running():
        morning_message_task.start()
    # Start the bump task
    if not bump_task.is_running():
        bump_task.start()

# Anti-Nuke: Track channel deletions
@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    # Try to get the audit log to find who deleted the channel
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            user = entry.user
            if user and user != bot.user:
                # Check if user is an admin
                if user.guild_permissions.administrator:
                    current_time = datetime.utcnow()
                    user_id = user.id
                    
                    # Add current deletion time
                    channel_deletion_times[user_id].append(current_time)
                    
                    # Remove deletions older than 60 seconds
                    channel_deletion_times[user_id] = [
                        t for t in channel_deletion_times[user_id]
                        if current_time - t <= timedelta(seconds=60)
                    ]
                    
                    # If 2 or more deletions within 60 seconds, ban the admin
                    if len(channel_deletion_times[user_id]) >= 2:
                        try:
                            await guild.ban(user, reason="Anti-nuke: Deleted 2+ channels within 60 seconds")
                            print(f"Banned {user} ({user_id}) for deleting 2+ channels within 60 seconds")
                            
                            # Send alert to a log channel (if exists)
                            log_channel = discord.utils.get(guild.text_channels, name='mod-log')
                            if not log_channel:
                                log_channel = discord.utils.get(guild.text_channels, name='logs')
                            
                            if log_channel:
                                embed = discord.Embed(
                                    title="🚨 Anti-Nuke Protection",
                                    description=f"**{user.mention}** has been banned for deleting 2+ channels within 60 seconds.",
                                    color=discord.Color.red(),
                                    timestamp=datetime.utcnow()
                                )
                                embed.add_field(name="User", value=f"{user} ({user_id})", inline=False)
                                embed.add_field(name="Channels Deleted", value=len(channel_deletion_times[user_id]), inline=False)
                                await log_channel.send(embed=embed)
                            
                            # Clear the tracking for this user
                            channel_deletion_times[user_id] = []
                        except discord.Forbidden:
                            print(f"Could not ban {user} - insufficient permissions")
                        except Exception as e:
                            print(f"Error banning {user}: {e}")
    except discord.Forbidden:
        print("No permission to view audit logs")
    except Exception as e:
        print(f"Error checking audit logs: {e}")

# Anti-Raid: Track member joins
@bot.event
async def on_member_join(member):
    guild = member.guild
    current_time = datetime.utcnow()
    
    # Add join time
    member_joins[guild.id].append(current_time)
    
    # Remove joins older than 10 seconds
    member_joins[guild.id] = [
        t for t in member_joins[guild.id]
        if current_time - t <= timedelta(seconds=10)
    ]
    
    # If 5 or more joins within 10 seconds, it might be a raid
    if len(member_joins[guild.id]) >= 5:
        # Lock down the server temporarily
        try:
            # Find a log channel
            log_channel = discord.utils.get(guild.text_channels, name='mod-log')
            if not log_channel:
                log_channel = discord.utils.get(guild.text_channels, name='logs')
            
            if log_channel:
                embed = discord.Embed(
                    title="⚠️ Possible Raid Detected",
                    description=f"{len(member_joins[guild.id])} members joined within 10 seconds!",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                await log_channel.send(embed=embed)
            
            # Clear the tracking
            member_joins[guild.id] = []
        except Exception as e:
            print(f"Error handling raid detection: {e}")

# Anti-Raid: Detect mass mentions
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Check for mass mentions (5+ mentions in one message)
    if len(message.mentions) >= 5:
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, mass mentions are not allowed!")
            
            # Warn or timeout the user
            try:
                await message.author.timeout(timedelta(minutes=10), reason="Mass mention spam")
            except:
                pass
        except discord.Forbidden:
            print("No permission to delete message or timeout user")
        except Exception as e:
            print(f"Error handling mass mention: {e}")
    
    # Check for spam (same message repeated 5+ times)
    if message.guild:
        channel = message.channel
        count = 0
        async for msg in channel.history(limit=10):
            if msg.author == message.author and msg.content == message.content:
                count += 1
        
        if count >= 5:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, spam is not allowed!")
                try:
                    await message.author.timeout(timedelta(minutes=10), reason="Spam")
                except:
                    pass
            except discord.Forbidden:
                print("No permission to delete spam message")
            except Exception as e:
                print(f"Error handling spam: {e}")
    
    # Process custom commands
    if message.content.startswith('!'):
        cmd_name = message.content.split()[0][1:].lower()
        if cmd_name in custom_commands:
            await message.channel.send(custom_commands[cmd_name])
            return
    
    await bot.process_commands(message)

# Custom Commands
@bot.command(name='addcmd', aliases=['addcommand'])
@commands.has_permissions(administrator=True)
async def add_command(ctx, command_name: str, *, response: str):
    """Add a custom command (Admin only)"""
    command_name = command_name.lower()
    if command_name in ['addcmd', 'delcmd', 'listcmd', 'help']:
        await ctx.send("❌ This command name is reserved!")
        return
    
    custom_commands[command_name] = response
    save_commands()
    await ctx.send(f"✅ Custom command `!{command_name}` has been added!")

@bot.command(name='delcmd', aliases=['deletecommand', 'removecommand'])
@commands.has_permissions(administrator=True)
async def delete_command(ctx, command_name: str):
    """Delete a custom command (Admin only)"""
    command_name = command_name.lower()
    if command_name in custom_commands:
        del custom_commands[command_name]
        save_commands()
        await ctx.send(f"✅ Custom command `!{command_name}` has been deleted!")
    else:
        await ctx.send(f"❌ Command `!{command_name}` not found!")

@bot.command(name='listcmd', aliases=['listcommands'])
async def list_commands(ctx):
    """List all custom commands"""
    if not custom_commands:
        await ctx.send("No custom commands have been added yet!")
        return
    
    embed = discord.Embed(
        title="Custom Commands",
        description="\n".join([f"`!{cmd}`" for cmd in custom_commands.keys()]),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Utility Commands
@bot.command(name='ping')
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.command(name='info')
async def info(ctx):
    """Bot information"""
    embed = discord.Embed(
        title="🛡️ Anti-Raid & Anti-Nuke Bot",
        description="Protecting your server from raids and nukes!",
        color=discord.Color.green()
    )
    embed.add_field(name="Features", value="• Anti-Raid Protection\n• Anti-Nuke Protection\n• Custom Commands\n• Spam Detection", inline=False)
    embed.add_field(name="Prefix", value="!", inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='avatar', aliases=['av', 'pfp', 'profilepic'])
async def avatar(ctx, member: discord.Member = None):
    """Display a user's avatar
    Usage: !avatar [user mention or user ID]
    If no user is mentioned, shows your own avatar."""
    # If no member is mentioned, use the command author
    if member is None:
        member = ctx.author
    
    # Get avatar URL
    avatar_url = member.display_avatar.url
    
    # Create simple embed with only the avatar image
    embed = discord.Embed()
    embed.set_image(url=avatar_url)
    
    await ctx.send(embed=embed)

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    """Clear messages (Mod only)"""
    if amount > 100:
        amount = 100
    try:
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"✅ Cleared {amount} messages!", delete_after=5)
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to delete messages!")

@bot.command(name='text', aliases=['send', 'say'])
@commands.has_permissions(administrator=True)
async def send_text(ctx, channel_input: str, *, message: str = None):
    """Send a message to a specified channel (Admin only)
    Usage: !text <channel name or mention> <message>
    Examples:
    - !text #general Hello everyone!
    - !text general This is a test message
    - !text 123456789012345678 Your message here"""
    try:
        channel = None
        
        # Check if channel is mentioned
        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        else:
            # Remove # if present
            channel_input_clean = channel_input.strip()
            if channel_input_clean.startswith('#'):
                channel_input_clean = channel_input_clean[1:]
            
            # Try to get by ID
            if channel_input_clean.isdigit():
                channel = bot.get_channel(int(channel_input_clean))
                if channel and channel.guild != ctx.guild:
                    channel = None
            # Try to get by name (exact match)
            else:
                channel = discord.utils.get(ctx.guild.text_channels, name=channel_input_clean)
            
            # If still not found, try partial name match (case-insensitive)
            if channel is None:
                for ch in ctx.guild.text_channels:
                    if channel_input_clean.lower() in ch.name.lower():
                        channel = ch
                        break
        
        # Validate channel
        if channel is None:
            await ctx.send(f"❌ Channel not found! Please mention a channel (e.g., `!text #general Your message`) or use the channel name.")
            return
        
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Please specify a text channel!")
            return
        
        # Check if message was provided
        if message is None or message.strip() == "":
            await ctx.send("❌ Please provide a message! Usage: `!text <channel> <message>`")
            return
        
        # Send the message to the specified channel
        try:
            await channel.send(message)
            await ctx.send(f"✅ Message sent to {channel.mention}!")
        except discord.Forbidden:
            await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}!")
        except Exception as e:
            await ctx.send(f"❌ Error sending message: {e}")
            
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error in send_text command: {e}")

# Morning Message Commands
@bot.command(name='setmorning', aliases=['morningchannel', 'setmorningchannel'])
@commands.has_permissions(administrator=True)
async def set_morning_channel(ctx, *, channel_input: str = None):
    """Set the channel for morning messages (Admin only)
    Usage: !setmorning [channel mention or channel name]
    Example: !setmorning #general or !setmorning general
    If no channel is specified, uses the current channel."""
    try:
        channel = None
        
        # If no input, use current channel
        if channel_input is None:
            channel = ctx.channel
        else:
            # Try to parse as channel mention or ID
            channel_input = channel_input.strip()
            
            # Check if user is trying to set a message instead of a channel
            # If the input is long or contains newlines, it's probably a message
            if len(channel_input) > 50 or '\n' in channel_input or '@' in channel_input:
                await ctx.send("❌ It looks like you're trying to set a morning message!\n"
                              "Use `!setmorningmsg <your message>` to set the message.\n"
                              "Use `!setmorning #channel` to set the channel.")
                return
            
            # Remove # if present
            if channel_input.startswith('#'):
                channel_input = channel_input[1:]
            
            # Try to find channel by mention, ID, or name
            # First, try to get from mentions
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            # Try to get by ID
            elif channel_input.isdigit():
                channel = bot.get_channel(int(channel_input))
                if channel and channel.guild != ctx.guild:
                    channel = None
            # Try to get by name (exact match)
            else:
                channel = discord.utils.get(ctx.guild.text_channels, name=channel_input)
            
            # If still not found, try partial name match (case-insensitive)
            if channel is None:
                for ch in ctx.guild.text_channels:
                    if channel_input.lower() in ch.name.lower():
                        channel = ch
                        break
        
        # Validate channel
        if channel is None:
            await ctx.send(f"❌ Channel not found! Please mention a channel (e.g., `!setmorning #general`) or use the channel name.")
            return
        
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Please specify a text channel!")
            return
        
        # Save the channel
        morning_channels[str(ctx.guild.id)] = channel.id
        save_morning_settings()
        await ctx.send(f"✅ Morning messages will be sent to {channel.mention}!")
        
    except Exception as e:
        await ctx.send(f"❌ Error setting morning channel: {e}")
        print(f"Error in set_morning_channel: {e}")

@bot.command(name='removemorning', aliases=['removemorningchannel'])
@commands.has_permissions(administrator=True)
async def remove_morning_channel(ctx):
    """Remove morning messages for this server (Admin only)"""
    if str(ctx.guild.id) in morning_channels:
        del morning_channels[str(ctx.guild.id)]
        if str(ctx.guild.id) in morning_messages:
            del morning_messages[str(ctx.guild.id)]
        save_morning_settings()
        await ctx.send("✅ Morning messages have been disabled for this server!")
    else:
        await ctx.send("❌ Morning messages are not set for this server!")

@bot.command(name='setmorningmsg', aliases=['morningmessage', 'custommorning'])
@commands.has_permissions(administrator=True)
async def set_morning_message(ctx, *, input_text: str = None):
    """Set a custom morning message (Admin only)
    Usage: !setmorningmsg [channel] <message>
    Examples:
    - !setmorningmsg Hello everyone!
    - !setmorningmsg #general Hello everyone!
    - !setmorningmsg (empty) - Reset to default message"""
    guild_id = str(ctx.guild.id)
    
    if input_text is None or input_text.strip() == "":
        if guild_id in morning_messages:
            del morning_messages[guild_id]
            save_morning_settings()
            await ctx.send("✅ Morning message reset to default!")
        else:
            await ctx.send("❌ No custom message was set!")
        return
    
    input_text = input_text.strip()
    channel = None
    message = None
    
    # Check if a channel is mentioned at the start
    if ctx.message.channel_mentions:
        # Channel mentioned - extract channel and message
        channel = ctx.message.channel_mentions[0]
        # Remove channel mention from message
        # Find the position after the channel mention
        channel_mention_text = channel.mention
        if input_text.startswith(channel_mention_text):
            message = input_text[len(channel_mention_text):].strip()
        else:
            # Try to find and remove channel mention
            message = input_text.replace(channel_mention_text, "", 1).strip()
    else:
        # Check if input starts with #channel-name pattern
        parts = input_text.split(None, 1)
        if len(parts) > 1 and parts[0].startswith('#'):
            # Try to find channel by name
            channel_name = parts[0][1:]  # Remove #
            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
            if channel:
                message = parts[1] if len(parts) > 1 else ""
            else:
                # Not a valid channel, treat as message
                message = input_text
        else:
            # No channel specified, use message as-is
            message = input_text
    
    # Validate message
    if not message or message.strip() == "":
        await ctx.send("❌ Please provide a message! Usage: `!setmorningmsg [channel] <message>`")
        return
    
    # Set channel if specified, otherwise use current or existing
    if channel:
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Please specify a text channel!")
            return
        morning_channels[guild_id] = channel.id
        save_morning_settings()
    elif guild_id not in morning_channels:
        # No channel set and none specified, use current channel
        morning_channels[guild_id] = ctx.channel.id
        save_morning_settings()
        channel = ctx.channel
    
    # Save the message
    morning_messages[guild_id] = message
    save_morning_settings()
    
    # Get channel for display
    if not channel:
        channel_id = morning_channels[guild_id]
        channel = bot.get_channel(channel_id) or ctx.channel
    
    await ctx.send(f"✅ Custom morning message set!\n**Preview:** {message}\n\n📌 **Channel:** {channel.mention}")

@bot.command(name='morninginfo')
async def morning_info(ctx):
    """Check morning message settings"""
    guild_id = str(ctx.guild.id)
    
    if guild_id not in morning_channels:
        # Check if message is set but channel is not
        if guild_id in morning_messages:
            await ctx.send("❌ Morning message is set, but no channel is configured!\n"
                          f"Use `!setmorning #channel` or `!setmorning` to set the channel.\n"
                          f"Or use `!setmorningmsg` again to automatically set this channel.")
        else:
            await ctx.send("❌ Morning messages are not configured for this server!\n"
                          f"Use `!setmorning #channel` to set the channel first.")
        return
    
    channel_id = morning_channels[guild_id]
    channel = bot.get_channel(channel_id)
    
    embed = discord.Embed(
        title="🌅 Morning Message Settings",
        color=discord.Color.gold()
    )
    
    if channel:
        embed.add_field(name="Channel", value=channel.mention, inline=False)
    else:
        embed.add_field(name="Channel", value="Channel not found!", inline=False)
    
    if guild_id in morning_messages:
        embed.add_field(name="Custom Message", value=morning_messages[guild_id], inline=False)
    else:
        embed.add_field(name="Custom Message", value="Using default message", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='testmorning', aliases=['morningtest'])
@commands.has_permissions(administrator=True)
async def test_morning(ctx):
    """Test the morning message (Admin only)"""
    guild_id = str(ctx.guild.id)
    
    if guild_id not in morning_channels:
        # Check if message is set but channel is not
        if guild_id in morning_messages:
            await ctx.send("❌ Morning message is set, but no channel is configured!\n"
                          f"Use `!setmorning #channel` or `!setmorning` to set the channel.\n"
                          f"Or use `!setmorningmsg` again to automatically set this channel.")
        else:
            await ctx.send("❌ Morning messages are not configured for this server!\n"
                          f"Use `!setmorning #channel` to set the channel first.")
        return
    
    channel_id = morning_channels[guild_id]
    channel = bot.get_channel(channel_id)
    
    if channel is None:
        await ctx.send("❌ Morning message channel not found!")
        return
    
    # Get custom message or use default
    if guild_id in morning_messages:
        message = morning_messages[guild_id]
    else:
        message = "🌅 Good morning everyone! Have a great day! 🌅"
    
    try:
        await channel.send(f"@everyone {message}")
        await ctx.send(f"✅ Test morning message sent to {channel.mention}!")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to send messages in that channel!")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# Track which servers already received morning message today
morning_sent_today = set()

# Morning Message Task - Check every hour
@tasks.loop(hours=1)
async def morning_message_task():
    """Send morning messages at 8:00 AM daily"""
    await bot.wait_until_ready()
    
    now = datetime.now()
    current_date = now.date()
    
    # Reset daily tracking at midnight
    if now.hour == 0:
        morning_sent_today.clear()
    
    # Send morning messages at 8 AM
    if now.hour == 8 and now.minute < 1:
        for guild_id_str, channel_id in morning_channels.items():
            # Check if we already sent today
            if guild_id_str in morning_sent_today:
                continue
                
            try:
                channel = bot.get_channel(channel_id)
                if channel is None:
                    continue
                
                guild_id = int(guild_id_str)
                guild = bot.get_guild(guild_id)
                if guild is None:
                    continue
                
                # Get custom message or use default
                if guild_id_str in morning_messages:
                    message = morning_messages[guild_id_str]
                else:
                    message = "🌅 Good morning everyone! Have a great day! 🌅"
                
                # Send message with @everyone mention
                await channel.send(f"@everyone {message}")
                morning_sent_today.add(guild_id_str)
                print(f"Sent morning message to {guild.name} in {channel.name}")
            except discord.Forbidden:
                print(f"No permission to send message in channel {channel_id}")
            except Exception as e:
                print(f"Error sending morning message: {e}")

# Start the task when bot is ready
@morning_message_task.before_loop
async def before_morning_task():
    await bot.wait_until_ready()
    # Wait until the next hour starts
    now = datetime.now()
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    wait_seconds = (next_hour - now).total_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

# Bump Channel Configuration
BUMP_CHANNEL_ID = 1454191176264585308
BUMP_APPLICATION_ID = 947088344167366698  # Application ID of the bot that owns /bump command

# Cache for command ID to avoid fetching every time
bump_command_id_cache = {}

async def get_bump_command_id(guild_id):
    """Fetch the actual command ID for /bump command"""
    if guild_id in bump_command_id_cache:
        return bump_command_id_cache[guild_id]
    
    try:
        url = f"https://discord.com/api/v10/applications/{BUMP_APPLICATION_ID}/guilds/{guild_id}/commands"
        headers = {
            "Authorization": f"Bot {bot.http.token}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    commands = await response.json()
                    # Find the /bump command
                    for cmd in commands:
                        if cmd.get("name") == "bump":
                            command_id = cmd.get("id")
                            bump_command_id_cache[guild_id] = command_id
                            print(f"✅ Found /bump command ID: {command_id}")
                            return command_id
                    print(f"⚠️  /bump command not found in application commands")
                    return None
                else:
                    response_text = await response.text()
                    print(f"⚠️  Failed to fetch commands. Status: {response.status}, Response: {response_text}")
                    return None
    except Exception as e:
        print(f"❌ Error fetching command ID: {e}")
        return None

# Bump Task - Runs every 2 hours
@tasks.loop(hours=2)
async def bump_task():
    """Execute /bump slash command in the specified channel every 2 hours"""
    await bot.wait_until_ready()
    
    try:
        channel = bot.get_channel(BUMP_CHANNEL_ID)
        if channel is None:
            print(f"⚠️  Bump channel {BUMP_CHANNEL_ID} not found!")
            return
        
        guild = channel.guild
        if guild is None:
            print(f"⚠️  Channel {BUMP_CHANNEL_ID} is not in a guild!")
            return
        
        # Get the actual command ID
        command_id = await get_bump_command_id(guild.id)
        if command_id is None:
            print(f"⚠️  Could not find /bump command ID. Skipping this run.")
            return
        
        # Execute the slash command using Discord's interaction API
        url = f"https://discord.com/api/v10/interactions"
        headers = {
            "Authorization": f"Bot {bot.http.token}",
            "Content-Type": "application/json"
        }
        
        # Create interaction payload for slash command
        payload = {
            "type": 2,  # APPLICATION_COMMAND
            "application_id": str(BUMP_APPLICATION_ID),
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "data": {
                "id": str(command_id),  # Use the actual command ID
                "name": "bump",
                "type": 1  # CHAT_INPUT
            }
        }
        
        # Use aiohttp to make the request
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 204:
                    print(f"✅ Executed /bump command in channel {channel.name} (ID: {BUMP_CHANNEL_ID})")
                elif response.status == 401:
                    print(f"❌ Authentication failed. Check bot token.")
                elif response.status == 403:
                    print(f"❌ Forbidden. Bot may not have permission to execute this command.")
                elif response.status == 400:
                    response_text = await response.text()
                    print(f"❌ Bad request. Response: {response_text}")
                    print(f"   Note: Discord bots cannot directly execute other bots' slash commands.")
                    print(f"   This is a Discord API limitation.")
                else:
                    response_text = await response.text()
                    print(f"⚠️  Failed to execute /bump command. Status: {response.status}, Response: {response_text}")
                    
    except discord.Forbidden:
        print(f"❌ No permission to execute commands in bump channel {BUMP_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Error executing bump command: {e}")

# Start the bump task when bot is ready
@bump_task.before_loop
async def before_bump_task():
    await bot.wait_until_ready()

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore command not found errors
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error}")
    else:
        print(f"Error: {error}")
        # Send user-friendly error message
        await ctx.send(f"❌ An error occurred: {str(error)}")

# Run the bot
if __name__ == "__main__":
    # Get token from environment variable or config
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("⚠️  Warning: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please set it or create a .env file with your token.")
        TOKEN = input("Enter your Discord bot token: ").strip()
    
    if TOKEN:
        webserver.keep_alive()  # Start Flask server in background thread
        bot.run(TOKEN)          # Then run Discord bot
    else:
        print("❌ No token provided. Exiting...")


