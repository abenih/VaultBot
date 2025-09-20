import os
import logging
import time

import openai

from openai import APIError, RateLimitError

import tempfile
import os

from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, JobQueue
)

from database import (
    init_db, user_exists, set_master_password, verify_master_password,
    save_voice_memo, get_user_memos, get_memo_file_id, delete_memo,
    get_db_connection
)


from dotenv import load_dotenv
load_dotenv()


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


LEMONFOX_API_KEY = os.getenv("LEMONFOX_API_KEY")
lemonfox_client = None
if LEMONFOX_API_KEY:
    try:
        
        lemonfox_client = openai.OpenAI(
            api_key=LEMONFOX_API_KEY,
            base_url="https://api.lemonfox.ai/v1" 
        )
        logger.info("OpenAI client configured for LemonFox.ai")
    except Exception as e:
        logger.error(f"❌ Failed to configure LemonFox client: {e}")
else:
    logger.warning("⚠️ LEMONFOX_API_KEY not found in environment variables. AI features will be disabled or fail.")


AWAITING_PASSWORD = 1
AWAITING_LOGIN = 2
AWAITING_VOICE = 3


user_activity = {}

user_last_messages = {}

# --- Inline keyboards ---
def get_start_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start VaultBot", callback_data="start_bot")]
    ])

def get_auth_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 Unlock Vault", callback_data="unlock_vault")]
    ])

def get_main_menu_inline_keyboard():
    """Vertical inline keyboard for main menu options"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 New Memo", callback_data="new_memo")],
        [InlineKeyboardButton("📋 My Memos", callback_data="my_memos")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
        [InlineKeyboardButton("🔐 Lock Vault", callback_data="lock_vault")]
    ])

def get_help_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Contact Support", url="https://t.me/abeni_h")],
        [InlineKeyboardButton("🚀 Start Over", callback_data="start_bot")]
    ])

def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ])

def get_memo_options_keyboard(memo_id):
    """Keyboard with options for a specific memo"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{memo_id}"),
            InlineKeyboardButton("📝 Transcribe", callback_data=f"transcribe_{memo_id}")
        ],
        [
            InlineKeyboardButton("✨ Summarize", callback_data=f"summarize_{memo_id}"),
            InlineKeyboardButton("🔙 Back to List", callback_data="back_to_memos")
        ],
        [InlineKeyboardButton("🏠 Back to Menu", callback_data="back_to_menu")]
    ])

# --- Utility Functions ---
async def cleanup_old_messages(context, user_id, chat_id, exclude_message_id=None):
    """Clean up old messages for a user, excluding a specific message if provided"""
    if user_id in user_last_messages:
        messages_to_delete = []
        for msg_id in user_last_messages[user_id][:]: # Iterate over a copy
            if exclude_message_id is not None and msg_id == exclude_message_id:
                continue
            messages_to_delete.append(msg_id)

        for msg_id in messages_to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                user_last_messages[user_id].remove(msg_id)
            except Exception as e:
                logger.warning(f"Could not delete message {msg_id} for user {user_id}: {e}")

        
        if len(user_last_messages[user_id]) > 10:
            user_last_messages[user_id] = user_last_messages[user_id][-5:]

def update_user_activity(user_id):
    
    user_activity[user_id] = time.time()

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    
    current_time = time.time()
    inactive_users = []

    for user_id, last_activity in list(user_activity.items()): # Use list() to avoid RuntimeError during iteration
        if current_time - last_activity > 300:  # 5 minutes
            inactive_users.append(user_id)

    for user_id in inactive_users:
       
        if user_id in user_activity:
            del user_activity[user_id]

        
        if user_id in user_last_messages:
            del user_last_messages[user_id]

        logger.info(f"User {user_id} vault locked due to inactivity")
        

# --- Main Bot Class ---
class VaultBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("❌ CRITICAL: No BOT_TOKEN found in environment variables")
            raise ValueError("Bot token not found in environment variables")

        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()

       
        self.job_queue = self.application.job_queue
        if self.job_queue:
             self.job_queue.run_repeating(check_inactivity, interval=60, first=10)
        else:
             logger.warning("JobQueue not available, inactivity check disabled.")

    def setup_handlers(self):
        """Set up all message handlers"""
       
        self.application.add_handler(CommandHandler("start", self.start_command_handler))

        self.application.add_handler(CallbackQueryHandler(self.transcribe_memo_handler, pattern=r'^transcribe_\d+$'))
        self.application.add_handler(CallbackQueryHandler(self.summarize_memo_handler, pattern=r'^summarize_\d+$'))

        self.application.add_handler(CallbackQueryHandler(self.inline_button_handler, pattern=".*"))

        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))

    
    async def start_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data.clear()
        user_id = update.effective_user.id
        update_user_activity(user_id)
        await cleanup_old_messages(context, user_id, update.effective_chat.id)
        await self.show_welcome_message(update, context)

    async def show_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        welcome_text = (
            "🔒 Welcome to VaultBot! 🔒\n\n"
            "Your secure, voice-based journal.\nEquiped with AI assisted transciption and summerization[openai's whisper model]\n"
            "Click the button below to get started:"
        )
        if update.message:
            message = await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_start_inline_keyboard())
            user_id = update.effective_user.id
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
        else: # Callback query
            query = update.callback_query
            await query.edit_message_text(welcome_text, parse_mode='HTML', reply_markup=get_start_inline_keyboard())

    async def inline_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        update_user_activity(user_id)
        current_message_id = query.message.message_id
        await cleanup_old_messages(context, user_id, query.message.chat_id, current_message_id)

        # Route based on callback_data
        if query.data == "start_bot":
            await self.start_bot(query, context)
        elif query.data == "unlock_vault":
            await self.unlock_vault(query, context)
        elif query.data == "new_memo":
            await self.new_memo_handler(query, context)
        elif query.data == "my_memos":
            await self.my_memos_handler(query, context)
        elif query.data == "help":
            await self.help_handler(query, context)
        elif query.data == "lock_vault":
            await self.lock_handler(query, context)
        elif query.data == "back_to_menu":
            await self.back_to_menu_handler(query, context)
        elif query.data == "back_to_memos":
            await self.my_memos_handler(query, context)
        elif query.data.startswith("listen_"):
            await self.listen_memo_handler(query, context)
        elif query.data.startswith("delete_"):
            await self.delete_memo_handler(query, context)
        # transcribe_ and summarize_ are handled by dedicated handlers

    async def start_bot(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = query.from_user.id
        if not user_exists(user_id):
            await query.edit_message_text("🔒 Welcome to VaultBot! 🔒\n\nYour secure, voice-based journal.\n\n📝 Please set your master password:", parse_mode='HTML')
            context.user_data['state'] = AWAITING_PASSWORD
        else:
            await query.edit_message_text("🔒 Vault is locked.\n\nPlease enter your master password to unlock:", parse_mode='HTML')
            context.user_data['state'] = AWAITING_LOGIN

    async def unlock_vault(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = query.from_user.id
        if user_exists(user_id):
            await query.edit_message_text("🔒 Vault is locked.\n\nPlease enter your master password to unlock:", parse_mode='HTML')
            context.user_data['state'] = AWAITING_LOGIN
        else:
            await query.edit_message_text("You need to set up your vault first!\n\nClick the button below to get started:", parse_mode='HTML', reply_markup=get_start_inline_keyboard())

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        text = update.message.text
        current_state = context.user_data.get('state')
        update_user_activity(user_id)
        await cleanup_old_messages(context, user_id, update.effective_chat.id)
        logger.info(f"User {user_id} in state {current_state} entered text: {text}")

        if current_state == AWAITING_PASSWORD:
            await self.handle_password_input(update, context, text)
        elif current_state == AWAITING_LOGIN:
            await self.handle_login_input(update, context, text)

    async def handle_password_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        user_id = update.effective_user.id
        if len(password) < 6:
            message = await update.message.reply_text("❌ Password must be at least 6 characters long.\nPlease try again:", reply_markup=ReplyKeyboardRemove())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            return
        if set_master_password(user_id, password):
            message = await update.message.reply_text("✅ Password set successfully!\n\n🔓 Your vault is now secured and ready to use.\n\nWhat would you like to do?", parse_mode='HTML', reply_markup=get_main_menu_inline_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            message = await update.message.reply_text("❌ Failed to set password. Please try again.", parse_mode='HTML')
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)

    async def handle_login_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        user_id = update.effective_user.id
        if verify_master_password(user_id, password):
            message = await update.message.reply_text("✅ Access granted!\n\n🔓 Your vault is now unlocked.\n\nWhat would you like to do?", parse_mode='HTML', reply_markup=get_main_menu_inline_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            message = await update.message.reply_text("❌ Incorrect password.\n\nPlease try again:", parse_mode='HTML', reply_markup=get_auth_inline_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        update_user_activity(user_id)
        await cleanup_old_messages(context, user_id, update.effective_chat.id)

        if not context.user_data.get('authenticated') or context.user_data.get('state') != AWAITING_VOICE:
            message = await update.message.reply_text("🔒 Please start by unlocking your vault and selecting 'New Memo'.", parse_mode='HTML', reply_markup=get_auth_inline_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            return

        voice = update.message.voice
        file_id = voice.file_id

        if save_voice_memo(user_id, file_id):
            message = await update.message.reply_text("✅ Memo saved!\n\nYour voice message has been securely stored.", parse_mode='HTML', reply_markup=get_back_to_menu_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            context.user_data['state'] = None
        else:
            message = await update.message.reply_text("❌ Failed to save memo. Please try again.", parse_mode='HTML', reply_markup=get_main_menu_inline_keyboard())
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)

    async def new_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.user_data.get('authenticated'):
            await query.edit_message_text("🔒 Please unlock your vault first!", parse_mode='HTML', reply_markup=get_auth_inline_keyboard())
            return
        context.user_data['state'] = AWAITING_VOICE
        await query.edit_message_text("🎤 Ready to record your memo!\n\nPlease send a voice message now.", parse_mode='HTML')

    async def my_memos_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.user_data.get('authenticated'):
            await query.edit_message_text("🔒 Please unlock your vault first!", parse_mode='HTML', reply_markup=get_auth_inline_keyboard())
            return

        user_id = query.from_user.id
        memos = get_user_memos(user_id)

        if not memos:
            await query.edit_message_text("📋 You don't have any memos yet.\n\nUse the 'New Memo' button to create your first voice memo!", parse_mode='HTML', reply_markup=get_main_menu_inline_keyboard())
            return

        keyboard = []
        for memo in memos:
            memo_date = memo['date'].split()[0] if ' ' in memo['date'] else memo['date']
            keyboard.append([InlineKeyboardButton(f"🎵 Memo {memo['id']} ({memo_date})", callback_data=f"listen_{memo['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])

        await query.edit_message_text("📋 Your memos:\n\nSelect a memo to listen to it:", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def listen_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id

        try:
            memo_id = int(query.data.replace("listen_", ""))
        except ValueError:
            await query.answer("Invalid memo ID")
            return

        file_id = get_memo_file_id(memo_id, user_id)
        if not file_id:
            await query.answer("Memo not found or access denied", show_alert=True)
            return

        try:
            voice_message = await context.bot.send_voice(chat_id=chat_id, voice=file_id)
            if user_id not in user_last_messages: user_last_messages[user_id] = []
            user_last_messages[user_id].append(voice_message.message_id)
            await query.answer("Playing your memo...")
        except Exception as e:
            logger.error(f"Error sending voice message: {e}")
            await query.answer("Error playing memo", show_alert=True)
            return

        memo_date = ""
        memos = get_user_memos(user_id)
        for memo in memos:
            if memo['id'] == memo_id:
                memo_date = memo['date'].split()[0] if ' ' in memo['date'] else memo['date']
                break

        options_message = await context.bot.send_message(chat_id=chat_id, text=f"🔊 Memo #{memo_id} ({memo_date})\n\nWhat would you like to do with this memo?", parse_mode='HTML', reply_markup=get_memo_options_keyboard(memo_id))
        if user_id not in user_last_messages: user_last_messages[user_id] = []
        user_last_messages[user_id].append(options_message.message_id)

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            if user_id in user_last_messages and message_id in user_last_messages[user_id]:
                user_last_messages[user_id].remove(message_id)
        except Exception as e:
            logger.warning(f"Could not delete memo list message: {e}")

    async def delete_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = query.from_user.id
        try:
            memo_id = int(query.data.replace("delete_", ""))
        except ValueError:
            await query.answer("Invalid memo ID")
            return
        if delete_memo(memo_id, user_id):
            await query.answer(f"Memo #{memo_id} deleted")
            await self.my_memos_handler(query, context) # Refresh list
        else:
            await query.answer("Failed to delete memo", show_alert=True)

    # --- AI Feature Handlers ---
    async def transcribe_memo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle transcription of a memo using LemonFox Whisper API"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        update_user_activity(user_id) # Update activity on interaction

        if not LEMONFOX_API_KEY or not lemonfox_client:
            await query.edit_message_text("❌ AI features are not configured. Please check the bot setup.", reply_markup=get_main_menu_inline_keyboard())
            await query.answer("AI Not Configured", show_alert=True)
            return

        try:
            memo_id = int(query.data.split('_')[1])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid memo ID.", reply_markup=get_main_menu_inline_keyboard())
            return

        # Fetch file_id and check ownership
        file_id = get_memo_file_id(memo_id, user_id)
        if not file_id:
            await query.edit_message_text("❌ Memo not found or access denied.", reply_markup=get_main_menu_inline_keyboard())
            return

        # Check if already transcribed
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT transcription FROM memos WHERE id = ? AND user_id = ?", (memo_id, user_id))
            row = cursor.fetchone()
            if row and row[0]:
                transcription = row[0]
                await query.edit_message_text(text=f"📝 Already transcribed:\n\n{transcription}", reply_markup=get_memo_options_keyboard(memo_id))
                return
        finally:
            if conn:
                conn.close()

        # --- Transcription Process ---
        tmp_path = None
        try:
            await query.edit_message_text("⏳ Transcribing your memo... Please wait.")

            file = await context.bot.get_file(file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
                await file.download_to_drive(tmp_file.name)
                tmp_path = tmp_file.name

           
            logger.info(f"Calling LemonFox Whisper for memo {memo_id} (user {user_id})")
            with open(tmp_path, "rb") as audio_file:
                
                transcript_response = lemonfox_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json" 
                )

            transcription_text = transcript_response.text.strip()
            detected_language = getattr(transcript_response, 'language', "unknown") # Safer way to get attribute

            logger.info(f"LemonFox Whisper transcription complete for memo {memo_id}. Language: {detected_language}")

            
            if not transcription_text:
                warning_msg = (
                    f"⚠️ Transcription resulted in empty text.\n"
                    f"Detected language: {detected_language}.\n"
                    f"The language might not be supported or the audio quality might be poor."
                )
                logger.warning(f"Empty transcription for memo {memo_id} (user {user_id}). Language: {detected_language}")
                await query.edit_message_text(warning_msg, reply_markup=get_memo_options_keyboard(memo_id))
                await query.answer("Transcription Warning", show_alert=True)
                return

            # Save to DB
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE memos SET transcription = ? WHERE id = ? AND user_id = ?", (transcription_text, memo_id, user_id))
            conn.commit()
            conn.close()

            
            await query.edit_message_text(text=f"📝 Transcription:\n\n{transcription_text}", reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("✅ Transcription complete!")

        except RateLimitError:
            logger.error(f"LemonFox Rate Limit exceeded for user {user_id} on memo {memo_id}")
            error_msg = "❌ Transcription failed: Rate limit exceeded. Please try again later."
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("Rate Limit", show_alert=True)
        except APIError as api_err: 
            logger.error(f"LemonFox API Error for user {user_id} on memo {memo_id}: {api_err}")
            error_msg = f"❌ Transcription failed: API Error - {str(api_err)[:150]}"
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("API Error", show_alert=True)
        except FileNotFoundError:
             logger.error(f"Temporary file not found for memo {memo_id} (user {user_id})")
             error_msg = "❌ Transcription failed: Could not process audio file."
             await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
             await query.answer("File Error", show_alert=True)
        except Exception as e:
            logger.error(f"Unexpected error during transcription for memo {memo_id}, user {user_id}: {e}", exc_info=True)
            error_msg = f"❌ Transcription failed unexpectedly: {str(e)[:200]}"
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("Transcription Failed", show_alert=True)
        finally:
            
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as e:
                     logger.warning(f"Could not delete temporary file {tmp_path}: {e}")

    async def summarize_memo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle summarization of a memo using LemonFox LLM"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        update_user_activity(user_id) 

        if not LEMONFOX_API_KEY or not lemonfox_client:
            await query.edit_message_text("❌ AI features are not configured. Please check the bot setup.", reply_markup=get_main_menu_inline_keyboard())
            await query.answer("AI Not Configured", show_alert=True)
            return

        try:
            memo_id = int(query.data.split('_')[1])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid memo ID.", reply_markup=get_main_menu_inline_keyboard())
            return

        
        conn = None
        transcription_text = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            
            cursor.execute("SELECT transcription FROM memos WHERE id = ? AND user_id = ?", (memo_id, user_id))
            row = cursor.fetchone()
            if row and row[0]:
                transcription_text = row[0]
            else:
               
                logger.info(f"No transcription found for memo {memo_id}, triggering transcription first.")
                
                update.callback_query.data = f"transcribe_{memo_id}"
                await self.transcribe_memo_handler(update, context)
               
                return

            # Check if already summarized
            cursor.execute("SELECT summary FROM memos WHERE id = ? AND user_id = ?", (memo_id, user_id))
            row = cursor.fetchone()
            if row and row[0]:
                summary = row[0]
                await query.edit_message_text(text=f"📝 Transcription:\n\n{transcription_text}\n\n✨ Summary:\n\n{summary}", reply_markup=get_memo_options_keyboard(memo_id))
                await query.answer("✅ Summary loaded!")
                return

        finally:
            if conn:
                conn.close()

        # --- Summarization Process ---
        try:
            await query.edit_message_text("🧠 Generating summary... Please wait.")

            
            logger.info(f"Calling LemonFox LLM for summary of memo {memo_id} (user {user_id})")
            
            response = lemonfox_client.chat.completions.create(
                model="llama3-8b", 
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes voice memos concisely."},
                    {"role": "user", "content": f"Please provide a concise one-paragraph summary of the following text:\n\n{transcription_text}"}
                ],
                temperature=0.3,
                max_tokens=200 
            )
            summary = response.choices[0].message.content.strip()
            logger.info(f"LemonFox LLM summary complete for memo {memo_id}.")

            # Save to DB
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE memos SET summary = ? WHERE id = ? AND user_id = ?", (summary, memo_id, user_id))
            conn.commit()
            conn.close()

            # Update message with transcription and summary
            await query.edit_message_text(text=f"📝 Transcription:\n\n{transcription_text}\n\n✨ Summary:\n\n{summary}", reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("✅ Summary generated!")

        except RateLimitError:
            logger.error(f"LemonFox Rate Limit exceeded for user {user_id} on memo {memo_id} (summarization)")
            error_msg = "❌ Summarization failed: Rate limit exceeded. Please try again later."
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("Rate Limit", show_alert=True)
        except APIError as api_err: # Catches other LemonFox API issues
            logger.error(f"LemonFox API Error for user {user_id} on memo {memo_id} (summarization): {api_err}")
            error_msg = f"❌ Summarization failed: API Error - {str(api_err)[:150]}"
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("API Error", show_alert=True)
        except Exception as e:
            logger.error(f"Unexpected error during summarization for memo {memo_id}, user {user_id}: {e}", exc_info=True)
            error_msg = f"❌ Summarization failed unexpectedly: {str(e)[:200]}"
            await query.edit_message_text(error_msg, reply_markup=get_memo_options_keyboard(memo_id))
            await query.answer("Summarization Failed", show_alert=True)

    # --- Other Handlers ---
    async def help_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = (
            "🤖 <b>VaultBot Help</b>\n\n"
            "• <b>🎤 New Memo</b>: Record a new voice memo\n"
            "• <b>📋 My Memos</b>: View your saved memos\n"
            "• <b>🔐 Lock Vault</b>: Lock your vault for security\n"
            "• <b>📝 Transcribe</b>: Convert speech to text (Powered by AI)\n"
            "• <b>✨ Summarize</b>: Get an AI summary of your memo\n\n"
            "Your data is encrypted and secure. Need more help?"
        )
        await query.edit_message_text(help_text, parse_mode='HTML', reply_markup=get_help_inline_keyboard())

    async def lock_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data['authenticated'] = False
        context.user_data['state'] = None
        user_id = query.from_user.id
        if user_id in user_activity:
            del user_activity[user_id]
        await cleanup_old_messages(context, user_id, query.message.chat_id)
        await query.edit_message_text("🔒 Vault locked.\n\nClick the button below to unlock when you're ready.", parse_mode='HTML', reply_markup=get_auth_inline_keyboard())

    async def back_to_menu_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        await query.edit_message_text("What would you like to do?", parse_mode='HTML', reply_markup=get_main_menu_inline_keyboard())

    def run(self):
        """Start the bot and initialize database"""
        if init_db():
            logger.info("Starting VaultBot...")
            self.application.run_polling()
        else:
            logger.error("Failed to initialize database. Bot cannot start.")

if __name__ == '__main__':
    try:
        bot = VaultBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
