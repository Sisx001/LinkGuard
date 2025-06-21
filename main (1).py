import os
import logging
from telegram import Bot, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackContext
)
import datetime
from functools import wraps

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration storage
CONFIG = {
    "source_chats": [], # List of source chat IDs/usernames
    "source_aliases": {}, # Dictionary mapping source_chat_id to its alias string
    "target_channel": None,
    "timer": 5,  # minutes
    "user_limit": 1,
    "message_template": "<b>Secure Access</b>: {invite_link}",
    "last_message_id": None,  # Track last message ID for deletion
    "active_job": None,  # Track active job
    "update_mode": "replace"  # "edit" or "replace"
}

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

# Security decorator for owner-only commands
def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if user_id != OWNER_ID:
            await update.message.reply_text("⛔ Unauthorized: This command is owner-only")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def is_valid_channel_identifier(identifier):
    """Check if identifier is valid (ID or username)"""
    return (identifier.startswith('@') or 
            identifier.startswith('-') or 
            identifier.lstrip('-').isdigit())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initial welcome with detailed command overview"""
    user_id = str(update.effective_user.id)
    help_text = """
🚀 <b>LinkGuard Bot - Admin Commands</b>

<u>Configuration Commands</u>
/set_channels &lt;target&gt; &lt;src_id&gt;[:"Alias"] [src_id2:"Alias2"...]
→ Set target channel & source groups. Aliases for sources are optional.
→ Target: Where links are posted. Sources: Where invites are made.
→ Use @username for public, ID for private. Bot must be admin.
→ Alias with spaces must be in quotes after colon. E.g., <code>@grp:"My Group"</code>
→ Example (no aliases):
  <code>/set_channels @link_ch @group_A -100123</code>
→ Example (with aliases):
  <code>/set_channels @link_ch @group_A:"Main Chat" @group_B:"Updates" -100123:"Private Archive"</code>

/set_timer &lt;minutes&gt;
→ Set link regeneration interval (minimum 1 minute)

/set_limit &lt;number&gt;
→ Set max users per link (minimum 1)

/set_template &lt;HTML text&gt;
→ Set message template with {invite_link} placeholder
→ <b>Supported HTML formatting</b>:
   <b>&lt;b&gt;Bold&lt;/b&gt;</b>
   <i>&lt;i&gt;Italic&lt;/i&gt;</i>
   <u>&lt;u&gt;Underline&lt;/u&gt;</u>
   <s>&lt;s&gt;Strikethrough&lt;/s&gt;</s>
   <code>&lt;code&gt;Monospace&lt;/code&gt;</code>
   <pre>&lt;pre&gt;Preformatted&lt;/pre&gt;</pre>
   <a href="https://example.com">&lt;a href="URL"&gt;Link&lt;/a&gt;</a>
→ Use <code>{links_list}</code> to show all generated invite links.
  Each link will be listed on a new line.
  If an alias is set for a source, it's used: "Alias Name: &lt;invite_url&gt;"
  Otherwise, the source ID is used: "<code>&lt;source_chat_id&gt;</code>: &lt;invite_url&gt;"
  (Or "Not available" if link generation failed for that source).
→ Example: <code>&lt;b&gt;Join our communities:&lt;/b&gt;\n{links_list}</code>
→ (Old <code>{invite_link}</code> placeholder shows only the first link if multiple sources are set)

<u>Operation Commands</u>
/start_posting → Begin auto-link regeneration
/stop_posting → Halt auto-regeneration
/toggle_update_mode → Switch between editing the post or sending a new one
/get_config → View current settings

<u>Post Update Behavior</u>
The bot can either <b>edit</b> the existing message with a new invite link or <b>delete</b> the old message and post a new one.
Use /toggle_update_mode to switch between these behaviors.
Current mode is shown in /get_config.
"""
    if user_id == OWNER_ID:
        await update.message.reply_text(help_text, parse_mode="HTML")
    else:
        await update.message.reply_text(
            "🔒 This bot is privately managed. Contact owner for assistance."
        )

@owner_only
async def set_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set target channel and one or more source groups by ID or username.
    Usage: /set_channels <target_id|@username> <source1_id|@username> [source2_id|@username]...
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ <b>Usage</b>: /set_channels &lt;target_channel&gt; &lt;source_chat_1&gt; [source_chat_2...]\n"
            "<b>Example (1 source)</b>:\n"
            "<code>/set_channels @my_public_channel @my_private_group</code>\n"
            "<b>Example (multiple sources)</b>:\n"
            "<code>/set_channels @my_public_channel @group_alpha -1001234567890</code>\n"
            "Ensure the bot is an admin in all specified channels/groups.",
            parse_mode="HTML"
        )
        return

    target_channel_arg = context.args[0]
    source_definitions_args = context.args[1:] # These can be "id" or "id:\"Alias\""

    if not is_valid_channel_identifier(target_channel_arg):
        await update.message.reply_text(f"❌ Invalid target channel identifier: {target_channel_arg}")
        return

    new_source_chats = []
    new_source_aliases = {}
    errors = []

    # Regex to parse "id_or_username:\"Alias Text\"" or "id_or_username:AliasText" or just "id_or_username"
    # It tries to capture the ID/username, and optionally the alias (which can be quoted or unquoted).
    # Unquoted aliases cannot contain colons. Quoted aliases are preferred for spaces/special chars.
    import re
    # Pattern: (id_or_username) (optional : (optional "alias_text" or alias_text_no_quote))
    # Group 1: chat_id_or_username
    # Group 3: quoted_alias (if quotes used)
    # Group 4: unquoted_alias (if no quotes used for alias)
    source_parser = re.compile(r'([^:]+)(?::(?:\"([^\"]+)\"|([^:]+)))?$')

    for src_def_arg in source_definitions_args:
        match = source_parser.fullmatch(src_def_arg)
        if not match:
            errors.append(f"Invalid format for source definition: <code>{src_def_arg}</code>")
            continue

        chat_id_or_username = match.group(1)
        alias = match.group(2) or match.group(3) # group(2) is quoted, group(3) is unquoted

        if not is_valid_channel_identifier(chat_id_or_username):
            errors.append(f"Invalid channel identifier in definition: <code>{chat_id_or_username}</code> (from <code>{src_def_arg}</code>)")
            continue

        new_source_chats.append(chat_id_or_username)
        if alias:
            # Basic sanitization for alias: strip leading/trailing whitespace
            alias = alias.strip()
            if alias: # Ensure alias is not just whitespace
                 new_source_aliases[chat_id_or_username] = alias

    if errors:
        await update.message.reply_text("❌ Errors found in source definitions:\n" + "\n".join(errors), parse_mode="HTML")
        return # Do not update config if there are errors

    if not new_source_chats:
        await update.message.reply_text("❌ No valid source channels provided or parsed.")
        return

    CONFIG["target_channel"] = target_channel_arg
    CONFIG["source_chats"] = new_source_chats
    CONFIG["source_aliases"] = new_source_aliases # Overwrite with new aliases

    sources_display_parts = []
    for src_id in CONFIG["source_chats"]:
        alias_text = CONFIG["source_aliases"].get(src_id)
        if alias_text:
            sources_display_parts.append(f"  - <code>{src_id}</code> (Alias: \"{alias_text}\")")
        else:
            sources_display_parts.append(f"  - <code>{src_id}</code>")
    sources_display = "\n".join(sources_display_parts)

    await update.message.reply_text(
        "✅ <b>Channels Configured</b>\n"
        f"<b>Target Channel</b>: <code>{CONFIG['target_channel']}</code>\n"
        f"<b>Source Chats & Aliases</b>:\n{sources_display}",
        parse_mode="HTML"
    )

@owner_only
async def set_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set regeneration interval"""
    try:
        minutes = int(context.args[0])
        if minutes < 1:
            raise ValueError
        CONFIG["timer"] = minutes
        await update.message.reply_text(f"⏰ Timer set to {minutes} minutes")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usage: /set_timer <minutes> (minimum 1)")

@owner_only
async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max users per link"""
    try:
        limit = int(context.args[0])
        if limit < 1:
            raise ValueError
        CONFIG["user_limit"] = limit
        await update.message.reply_text(f"👥 User limit set to {limit}")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usage: /set_limit <number> (minimum 1)")

@owner_only
async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set HTML message template with formatting support"""

    # Extract the template text more reliably for multi-line input
    command_text = "/set_template" # Assuming this is how the command is registered
    # Find the command in the message text to get its length accurately,
    # especially if it was called with the bot's username (e.g., /set_template@MyBotName)
    if update.message.entities and update.message.entities[0].type == "bot_command":
        command_entity = update.message.entities[0]
        actual_command_invoked = update.message.text[command_entity.offset : command_entity.offset + command_entity.length]
        # Use the length of the actual command invoked to split off the arguments
        raw_template_text = update.message.text[len(actual_command_invoked):].strip()
    else: # Fallback if not a typical command entity (e.g. testing, direct call)
        # This fallback might not be perfect if bot username is used without being an entity
        if update.message.text.lower().startswith(command_text):
             raw_template_text = update.message.text[len(command_text):].strip()
        else: # Should not happen if handler is correct
            logger.warning(f"Could not determine command in set_template: {update.message.text}")
            raw_template_text = " ".join(context.args) # Original method as last resort


    if not raw_template_text:
        await update.message.reply_text(
            "❌ Provide HTML template text after the command.\n"
            "Use {links_list} for all generated links or {invite_link} for the first one.\n"
            "Example:\n<code>/set_template &lt;b&gt;Join Us:&lt;/b&gt;\n{links_list}</code>",
            parse_mode="HTML"
        )
        return
    
    CONFIG["message_template"] = raw_template_text

    # Generate a more comprehensive preview
    preview_parts = [f"📝 <b>Template Set</b>", f"<b>Raw</b>: <code>{CONFIG['message_template']}</code>\n"]

    # Create dummy data for placeholders
    dummy_invite_link = "t.me/joinchat/DUMMYINVITE123"
    dummy_links_list_parts = [
        "My Channel Alias: t.me/joinchat/ALIASLINK",
        "<code>@dummy_source_id</code>: t.me/joinchat/IDLINK",
        "Another Alias: Not available"
    ]
    dummy_links_list_string = "\n".join(dummy_links_list_parts)

    preview_text_final = "Could not render preview (template might be missing placeholders or have other issues)."

    # Attempt to format with {links_list} first, then {invite_link} if applicable
    # This allows templates with both, though {links_list} is preferred.
    try:
        if "{links_list}" in CONFIG["message_template"]:
            # If other placeholders are present, format might fail.
            # We only provide {links_list} and {invite_link} for this preview.
            temp_preview_template = CONFIG["message_template"]
            # Provide both, but one might not be used by the template.
            available_placeholders = {"links_list": dummy_links_list_string, "invite_link": dummy_invite_link}

            # A simple way to fill only available placeholders to avoid KeyError for others
            # This isn't a full templating engine, so it's a basic preview.
            # For a more robust preview, one might need to parse the template for all placeholders.
            # For now, we will try to format with what we have.
            # A common issue is if template has e.g. {foo} but we don't provide dummy_foo.
            # We can try to provide them if they are known, or make the .format() more robust.

            # Simplistic approach: if it contains {links_list}, assume it's the primary.
            # If it also contains {invite_link}, that one will be ignored by .format if {links_list} is the only one used.
            # This is tricky. Let's try to format with both if both placeholders are in the template.
            # A better way is to replace known placeholders sequentially.

            # Create a dictionary of placeholders we can fill for the preview
            preview_format_args = {}
            preview_template_for_formatting = CONFIG["message_template"]

            if "{links_list}" in preview_template_for_formatting:
                preview_format_args["links_list"] = dummy_links_list_string
            if "{invite_link}" in preview_template_for_formatting:
                preview_format_args["invite_link"] = dummy_invite_link

            if not preview_format_args: # Neither known placeholder is in the template
                 preview_text_final = "Preview: (Template does not use {links_list} or {invite_link})"
            else:
                try:
                    # This will raise KeyError if other unknown placeholders exist
                    preview_text_final = preview_template_for_formatting.format(**preview_format_args)
                except KeyError as e:
                    logger.warning(f"KeyError during template preview formatting: {e}. User template might have other placeholders.")
                    preview_text_final = (f"Preview: (Could not fully render due to missing key: {e}. "
                                          f"Showing partial if possible, or check template for unknown placeholders like {{{e.key}}})")
                    # Try to replace known ones sequentially for a partial preview
                    temp_str = preview_template_for_formatting
                    if "{links_list}" in temp_str and "links_list" in preview_format_args:
                        temp_str = temp_str.replace("{links_list}", preview_format_args["links_list"])
                    if "{invite_link}" in temp_str and "invite_link" in preview_format_args:
                        temp_str = temp_str.replace("{invite_link}", preview_format_args["invite_link"])
                    preview_text_final = temp_str


        elif "{invite_link}" in CONFIG["message_template"]: # Only {invite_link}
            preview_text_final = CONFIG["message_template"].format(invite_link=dummy_invite_link)
        else:
            preview_text_final = CONFIG["message_template"] # No known placeholders, show as is

    except Exception as e:
        logger.error(f"Error during template preview generation: {e}")
        preview_text_final = f"Preview: (Error rendering preview: {e})"

    preview_parts.append(f"<b>Preview with dummy data</b> (actual output may vary based on # of sources and aliases):\n{preview_text_final}")

    await update.message.reply_text("\n".join(preview_parts), parse_mode="HTML", disable_web_page_preview=True)

async def generate_invite_link_for_chat(bot: Bot, chat_id: str):
    """Generate new invite link for a specific chat with current global config for timer/limit."""
    expire_time = datetime.datetime.now() + datetime.timedelta(minutes=CONFIG["timer"])
    try:
        result = await bot.create_chat_invite_link(
            chat_id=chat_id,
            expire_date=expire_time,
            member_limit=CONFIG["user_limit"]
        )
        logger.info(f"Successfully generated invite link for chat_id: {chat_id}")
        return result.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link for chat_id {chat_id}: {e}")
        return None

async def generate_all_invite_links(bot: Bot) -> list[str | None]:
    """Generates invite links for all configured source chats."""
    links = []
    for source_chat_id in CONFIG.get("source_chats", []):
        link = await generate_invite_link_for_chat(bot, source_chat_id)
        links.append(link) # Appends the link or None if generation failed
    return links

@owner_only
async def start_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Begin auto-posting with link regeneration"""
    # Validate configuration
    if not CONFIG.get("source_chats") or not CONFIG.get("target_channel"):
        await update.message.reply_text(
            "❌ Configure target channel and at least one source chat first using /set_channels"
        )
        return
    
    # Stop any existing job
    if CONFIG["active_job"]:
        CONFIG["active_job"].schedule_removal()
        CONFIG["active_job"] = None
    
    # Create first post immediately
    await post_new_link(context.bot, source="start_posting_initial")
    
    # Start regeneration job
    job = context.job_queue.run_repeating(
        post_new_link_job,
        interval=CONFIG["timer"] * 60,
        first=CONFIG["timer"] * 60,  # Wait for timer before next post
    )
    CONFIG["active_job"] = job
    logger.info(f"Job '{job.name}' scheduled. Next run at: {job.next_t}. Interval: {job.interval}s. Repeat: {job.repeat}")
    
    await update.message.reply_text("🔄 Auto-posting activated!")

async def post_new_link(bot: Bot, source: str = "unknown"):
    """Create new post with fresh link, either by editing or replacing."""
    logger.info(f"post_new_link called from: {source}") # Diagnostic log

    new_links_list = await generate_all_invite_links(bot) # Changed to get a list of links

    # Filter out None values in case some link generations failed
    valid_new_links = [link for link in new_links_list if link is not None]

    if not valid_new_links:
        logger.error(f"Failed to generate any valid invite links (called from {source})")
        # Optionally, notify the owner
        # await bot.send_message(chat_id=OWNER_ID, text="Error: Failed to generate any valid invite links.")
        return

    # Format the message using the new {links_list} placeholder
    # The actual links_list content is prepared based on valid_new_links and source_chats

    links_display_parts = []
    source_chat_ids = CONFIG.get("source_chats", [])
    source_aliases_map = CONFIG.get("source_aliases", {})

    for i, link_url in enumerate(new_links_list): # Iterate over original list to match with source_chat_ids
        source_id_or_username = source_chat_ids[i] if i < len(source_chat_ids) else f"Unknown Source {i+1}"
        display_name = source_aliases_map.get(source_id_or_username, f"<code>{source_id_or_username}</code>")

        # Ensure display_name is HTML-safe if it's an alias that might contain < or >
        # For simplicity, we assume aliases are plain text or already safe.
        # A more robust solution would use html.escape on aliases if they are user-provided free text.
        # However, since our alias parsing doesn't allow HTML tags within them, this might be okay.
        # If an alias itself is `<b>Cool</b>`, it will render as `<b>Cool</b>: link`.
        # If an alias is `Cool&Stuff`, it will render as `Cool&Stuff: link`.
        # The `<code>` tags are only for non-aliased IDs.

        if link_url: # If link generation was successful
            links_display_parts.append(f"{display_name}: {link_url}")
        else: # If link generation failed for this source
            links_display_parts.append(f"{display_name}: Not available")

    links_list_string = "\n".join(links_display_parts)

    if "{links_list}" in CONFIG["message_template"]:
        try:
            formatted_message = CONFIG["message_template"].format(links_list=links_list_string)
        except KeyError as e:
            logger.error(f"Message template formatting error. Likely missing other placeholders or bad template. Error: {e}")
            logger.warning("Falling back to default multi-link format due to template error.")
            formatted_message = f"<b>Updated Invite Links:</b>\n{links_list_string}"
    elif valid_new_links and "{invite_link}" in CONFIG["message_template"]: # Backward compatibility for old single link template
        logger.warning("Using old template with {invite_link} for multi-link scenario. Only first link will be shown.")
        formatted_message = CONFIG["message_template"].format(invite_link=valid_new_links[0])
    else:
        logger.info("No specific placeholder found. Using default multi-link format.")
        formatted_message = f"<b>Updated Invite Links:</b>\n{links_list_string}"

    update_mode = CONFIG.get("update_mode", "replace") # Default to replace if not set

    if update_mode == "edit" and CONFIG["last_message_id"]:
        try:
            await bot.edit_message_text(
                chat_id=CONFIG["target_channel"],
                message_id=CONFIG["last_message_id"],
                text=formatted_message,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            logger.info(f"Edited message ID: {CONFIG['last_message_id']} in chat {CONFIG['target_channel']} (link preview disabled)")
            return # Successfully edited, no need to update last_message_id
        except Exception as e:
            logger.error(f"Failed to edit message {CONFIG['last_message_id']}: {e}. Falling back to replace.")
            # Fallback to delete and send new if edit fails
            # No explicit 'else' needed here, will proceed to delete-and-send logic

    # "replace" mode or fallback from "edit"
    # Delete previous message if it exists
    if CONFIG["last_message_id"]:
        try:
            await bot.delete_message(
                chat_id=CONFIG["target_channel"],
                message_id=CONFIG["last_message_id"]
            )
            logger.info(f"Deleted previous message: {CONFIG['last_message_id']} for replacement.")
        except Exception as e:
            logger.error(f"Failed to delete message {CONFIG['last_message_id']} for replacement: {e}")
        finally:
            CONFIG["last_message_id"] = None # Ensure it's cleared even if deletion failed, to prevent issues

    # Send new message
    try:
        sent_message = await bot.send_message(
            chat_id=CONFIG["target_channel"],
            text=formatted_message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        CONFIG["last_message_id"] = sent_message.message_id
        logger.info(f"Posted new message ID: {sent_message.message_id} in chat {CONFIG['target_channel']} (link preview disabled)")
    except Exception as e:
        logger.error(f"Failed to post new message in {CONFIG['target_channel']}: {e}")
        # Optionally, notify the owner if posting fails
        # await bot.send_message(chat_id=OWNER_ID, text=f"Error: Failed to post new message to {CONFIG['target_channel']}.")


async def post_new_link_job(context: ContextTypes.DEFAULT_TYPE):
    """Job handler for posting new links"""
    logger.info(f"Job '{context.job.name}' triggered. Attempting to run post_new_link.")
    await post_new_link(context.bot, source="post_new_link_job_scheduled")

@owner_only
async def stop_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Halt auto-regeneration"""
    if not CONFIG["active_job"]:
        await update.message.reply_text("❌ No active posting job")
        return
    
    CONFIG["active_job"].schedule_removal()
    CONFIG["active_job"] = None
    await update.message.reply_text("⏹️ Auto-posting stopped")

@owner_only
async def toggle_update_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle message update mode between 'edit' and 'replace'."""
    current_mode = CONFIG.get("update_mode", "replace")
    new_mode = "edit" if current_mode == "replace" else "replace"
    CONFIG["update_mode"] = new_mode
    await update.message.reply_text(
        f"⚙️ Message update mode set to: <b>{new_mode.upper()}</b>\n\n"
        f"<b>EDIT Mode</b>: The bot will try to edit the last sent message with the new link.\n"
        f"<b>REPLACE Mode</b>: The bot will delete the old message and send a new one.",
        parse_mode="HTML"
    )

@owner_only
async def get_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current configuration"""
    config_text_template = """
⚙️ <b>Current Configuration</b>
    
<b>Source Chats</b>:
{cfg_source_chats_display}
<b>Target Channel</b>: <code>{cfg_target_channel}</code>
<b>Regeneration Timer</b>: {cfg_timer} minutes
<b>User Limit/Link</b>: {cfg_user_limit}
<b>Message Update Mode</b>: {disp_update_mode}
<b>Message Template</b>:
<code>{cfg_message_template}</code>
<b>Active Job</b>: {disp_job_status}
<b>Last Message ID</b>: {disp_last_message_id}
""" # Renamed placeholders

    job_status_display = "✅ Running" if CONFIG.get("active_job") else "❌ Stopped"
    last_message_id_display = CONFIG.get("last_message_id") or "None"
    update_mode_display = CONFIG.get("update_mode", "replace").upper()

    source_chats_list = CONFIG.get("source_chats", [])
    source_aliases_map = CONFIG.get("source_aliases", {})
    source_display_lines = []
    if source_chats_list:
        for src_id in source_chats_list:
            alias = source_aliases_map.get(src_id)
            if alias:
                source_display_lines.append(f"  - <code>{src_id}</code> (Alias: \"{alias}\")")
            else:
                source_display_lines.append(f"  - <code>{src_id}</code>")
        cfg_source_chats_display_val = "\n".join(source_display_lines)
    else:
        cfg_source_chats_display_val = "  No source chats configured."

    formatting_args = {
        "cfg_source_chats_display": cfg_source_chats_display_val,
        "cfg_target_channel": CONFIG.get("target_channel") or "Not Set",
        "cfg_timer": CONFIG.get("timer", 0),
        "cfg_user_limit": CONFIG.get("user_limit", 0),
        "disp_update_mode": update_mode_display,
        "cfg_message_template": CONFIG.get("message_template") or "Not Set",
        "disp_job_status": job_status_display,
        "disp_last_message_id": last_message_id_display
    }

    await update.message.reply_text(
        config_text_template.format(**formatting_args),
        parse_mode="HTML"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(msg="Exception while handling update:", exc_info=context.error)

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return
    
    if not OWNER_ID:
        logger.warning("OWNER_ID not set - all users can access admin commands!")
    
    # Create Application using ApplicationBuilder
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("set_channels", set_channels))
    app.add_handler(CommandHandler("set_timer", set_timer))
    app.add_handler(CommandHandler("set_limit", set_limit))
    app.add_handler(CommandHandler("set_template", set_template))
    app.add_handler(CommandHandler("start_posting", start_posting))
    app.add_handler(CommandHandler("stop_posting", stop_posting))
    app.add_handler(CommandHandler("get_config", get_config))
    app.add_handler(CommandHandler("toggle_update_mode", toggle_update_mode))
    
    # Error handling
    app.add_error_handler(error_handler)

    # Start polling
    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
