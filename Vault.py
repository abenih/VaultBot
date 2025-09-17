import os
import logging
import time
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, JobQueue
)
from database import init_db, user_exists, set_master_password, verify_master_password, save_voice_memo, get_user_memos, get_memo_file_id, delete_memo

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
AWAITING_PASSWORD = 1
AWAITING_LOGIN = 2
AWAITING_VOICE = 3  # New state for voice messages

# Global dictionary to track user activity
user_activity = {}
# Dictionary to track the last message IDs for each user
user_last_messages = {}

# Inline keyboards
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
        [InlineKeyboardButton("📞 Contact Support", url="https://t.me/your_support")],
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
            InlineKeyboardButton("🗑️ Delete This Memo", callback_data=f"delete_{memo_id}"),
            InlineKeyboardButton("🔙 Back to List", callback_data="back_to_memos")
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ])

async def cleanup_old_messages(context, user_id, chat_id, exclude_message_id=None):
    """Clean up old messages for a user, excluding a specific message if provided"""
    if user_id in user_last_messages:
        messages_to_delete = []
        for msg_id in user_last_messages[user_id]:
            if exclude_message_id is not None and msg_id == exclude_message_id:
                continue
            messages_to_delete.append(msg_id)
        
        for msg_id in messages_to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                user_last_messages[user_id].remove(msg_id)
            except Exception as e:
                logger.error(f"Error deleting message {msg_id} for user {user_id}: {e}")
        
        # If we have too many messages stored, clear the list
        if len(user_last_messages[user_id]) > 10:
            user_last_messages[user_id] = user_last_messages[user_id][-5:]

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Check for inactive users and lock their vaults"""
    current_time = time.time()
    inactive_users = []
    
    for user_id, last_activity in user_activity.items():
        if current_time - last_activity > 300:  # 5 minutes
            inactive_users.append(user_id)
    
    for user_id in inactive_users:
        # Get the chat_id from context (this might need to be stored separately)
        # For simplicity, we'll just remove from activity tracking
        # In a real implementation, you'd want to store chat_id along with user_id
        del user_activity[user_id]
        
        # Clear any stored messages for this user
        if user_id in user_last_messages:
            del user_last_messages[user_id]
        
        logger.info(f"User {user_id} vault locked due to inactivity")

class VaultBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("No BOT_TOKEN found in environment variables")
            raise ValueError("Bot token not found in environment variables")
            
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        
        # Set up inactivity check job
        self.job_queue = self.application.job_queue
        self.job_queue.run_repeating(check_inactivity, interval=60, first=10)  # Check every minute
        
    def setup_handlers(self):
        """Set up all message handlers"""
        # Add handler for /start command
        self.application.add_handler(CommandHandler("start", self.start_command_handler))
        
        # Add handler for inline button callbacks - use pattern matching
        self.application.add_handler(CallbackQueryHandler(self.inline_button_handler, pattern=".*"))
        
        # Add handler for text messages (for password input)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input)
        )
        
        # Add handler for voice messages
        self.application.add_handler(
            MessageHandler(filters.VOICE, self.handle_voice_message)
        )
        
    def update_user_activity(self, user_id):
        """Update the user's last activity timestamp"""
        user_activity[user_id] = time.time()
        
    async def start_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        # Clear any existing state
        context.user_data.clear()
        
        # Update user activity
        user_id = update.effective_user.id
        self.update_user_activity(user_id)
        
        # Clean up old messages
        await cleanup_old_messages(context, user_id, update.effective_chat.id)
        
        # Show welcome message
        await self.show_welcome_message(update, context)
    
    async def show_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show welcome message with start button"""
        welcome_text = (
            "🔒 Welcome to VaultBot! 🔒\n\n"
            "Your secure, voice-based journal.\n\n"
            "Click the button below to get started:"
        )
        
        # If this is a command, reply with a new message
        if update.message:
            message = await update.message.reply_text(
                welcome_text,
                parse_mode='HTML',
                reply_markup=get_start_inline_keyboard()
            )
            # Store the message ID
            user_id = update.effective_user.id
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
        # If this is a callback, edit the existing message
        else:
            query = update.callback_query
            await query.edit_message_text(
                welcome_text,
                parse_mode='HTML',
                reply_markup=get_start_inline_keyboard()
            )
    
    async def inline_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Update user activity
        user_id = query.from_user.id
        self.update_user_activity(user_id)
        
        # Store the current message ID to exclude it from cleanup
        current_message_id = query.message.message_id
        
        # Clean up old messages, excluding the current one
        await cleanup_old_messages(context, user_id, query.message.chat_id, current_message_id)
        
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
    
    async def start_bot(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start the bot flow"""
        user_id = query.from_user.id
        
        if not user_exists(user_id):
            # New user - prompt for password setup
            await query.edit_message_text(
                "🔒 Welcome to VaultBot! 🔒\n\n"
                "Your secure, voice-based journal.\n\n"
                "📝 Please set your master password:",
                parse_mode='HTML'
            )
            # Set state to await password
            context.user_data['state'] = AWAITING_PASSWORD
        else:
            # Existing user - prompt for login
            await query.edit_message_text(
                "🔒 Vault is locked.\n\n"
                "Please enter your master password to unlock:",
                parse_mode='HTML'
            )
            # Set state to await login
            context.user_data['state'] = AWAITING_LOGIN
    
    async def unlock_vault(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Unlock the vault"""
        user_id = query.from_user.id
        
        if user_exists(user_id):
            await query.edit_message_text(
                "🔒 Vault is locked.\n\n"
                "Please enter your master password to unlock:",
                parse_mode='HTML'
            )
            context.user_data['state'] = AWAITING_LOGIN
        else:
            await query.edit_message_text(
                "You need to set up your vault first!\n\n"
                "Click the button below to get started:",
                parse_mode='HTML',
                reply_markup=get_start_inline_keyboard()
            )
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text input (for password entry)"""
        user_id = update.effective_user.id
        text = update.message.text
        current_state = context.user_data.get('state')
        
        # Update user activity
        self.update_user_activity(user_id)
        
        # Clean up old messages
        await cleanup_old_messages(context, user_id, update.effective_chat.id)
        
        logger.info(f"User {user_id} in state {current_state} entered text: {text}")
        
        if current_state == AWAITING_PASSWORD:
            await self.handle_password_input(update, context, text)
        elif current_state == AWAITING_LOGIN:
            await self.handle_login_input(update, context, text)
        else:
            # If no state is set, just ignore the text input
            pass
    
    async def handle_password_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        """Handle new password input"""
        user_id = update.effective_user.id
        
        # Validate password strength
        if len(password) < 6:
            message = await update.message.reply_text(
                "❌ Password must be at least 6 characters long.\n"
                "Please try again:",
                reply_markup=ReplyKeyboardRemove()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            return
        
        # Set the master password
        if set_master_password(user_id, password):
            # Show main menu with inline keyboard
            message = await update.message.reply_text(
                "✅ Master password set successfully!\n\n"
                "🔓 Your vault is now secured and ready to use.\n\n"
                "What would you like to do?",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            
            # Clear state and mark as authenticated
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            message = await update.message.reply_text(
                "❌ Failed to set password. Please try again:",
                parse_mode='HTML'
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
    
    async def handle_login_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        """Handle login password input"""
        user_id = update.effective_user.id
        
        # Verify the password
        if verify_master_password(user_id, password):
            # Show main menu with inline keyboard
            message = await update.message.reply_text(
                "✅ Access granted!\n\n"
                "🔓 Your vault is now unlocked.\n\n"
                "What would you like to do?",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            
            # Clear state and mark as authenticated
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            message = await update.message.reply_text(
                "❌ Incorrect password.\n\n"
                "Please try again:",
                parse_mode='HTML',
                reply_markup=get_auth_inline_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages"""
        # Update user activity
        user_id = update.effective_user.id
        self.update_user_activity(user_id)
        
        # Clean up old messages
        await cleanup_old_messages(context, user_id, update.effective_chat.id)
        
        # Check if user is authenticated and in the correct state
        if not context.user_data.get('authenticated') or context.user_data.get('state') != AWAITING_VOICE:
            message = await update.message.reply_text(
                "🔒 Please start by unlocking your vault and selecting 'New Memo'.",
                parse_mode='HTML',
                reply_markup=get_auth_inline_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            return
        
        voice = update.message.voice
        file_id = voice.file_id
        
        # Save the voice memo to database
        if save_voice_memo(user_id, file_id):
            # Edit the current message to show success
            message = await update.message.reply_text(
                "✅ Memo saved!\n\n"
                "Your voice message has been securely stored.",
                parse_mode='HTML',
                reply_markup=get_back_to_menu_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)
            
            # Clear the voice state
            context.user_data['state'] = None
        else:
            message = await update.message.reply_text(
                "❌ Failed to save memo. Please try again.",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            # Store the message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(message.message_id)

    async def new_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle New Memo button press"""
        # Check if user is authenticated
        if not context.user_data.get('authenticated'):
            await query.edit_message_text(
                "🔒 Please unlock your vault first!",
                parse_mode='HTML',
                reply_markup=get_auth_inline_keyboard()
            )
            return
        
        # Set state to await voice message
        context.user_data['state'] = AWAITING_VOICE
        
        await query.edit_message_text(
            "🎤 Ready to record your memo!\n\n"
            "Please send a voice message now.",
            parse_mode='HTML'
        )

    async def my_memos_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle My Memos button press"""
        # Check if user is authenticated
        if not context.user_data.get('authenticated'):
            await query.edit_message_text(
                "🔒 Please unlock your vault first!",
                parse_mode='HTML',
                reply_markup=get_auth_inline_keyboard()
            )
            return
        
        user_id = query.from_user.id
        memos = get_user_memos(user_id)
        
        if not memos:
            await query.edit_message_text(
                "📋 You don't have any memos yet.\n\n"
                "Use the 'New Memo' button to create your first voice memo!",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            return
        
        # Create inline keyboard with listen buttons for each memo
        keyboard = []
        for memo in memos:
            # Format date for display
            memo_date = memo['date'].split()[0] if ' ' in memo['date'] else memo['date']
            keyboard.append([
                InlineKeyboardButton(
                    f"🎵 Memo {memo['id']} ({memo_date})", 
                    callback_data=f"listen_{memo['id']}"
                )
            ])
        
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "📋 Your memos:\n\n"
            "Select a memo to listen to it:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def listen_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle listening to a specific memo"""
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id  # The message that contains the memo list

        # Extract memo ID from callback data
        try:
            memo_id = int(query.data.replace("listen_", ""))
        except ValueError:
            await query.answer("Invalid memo ID")
            return

        # Get the file_id for this memo
        file_id = get_memo_file_id(memo_id, user_id)

        if not file_id:
            await query.answer("Memo not found or access denied", show_alert=True)
            return

        # Send the voice message without caption
        try:
            voice_message = await context.bot.send_voice(
                chat_id=chat_id,
                voice=file_id
                # Removed the caption parameter to eliminate "Playing memo #3" text
            )
            # Store the voice message ID
            if user_id not in user_last_messages:
                user_last_messages[user_id] = []
            user_last_messages[user_id].append(voice_message.message_id)
            
            await query.answer("Playing your memo...")
        except Exception as e:
            logger.error(f"Error sending voice message: {e}")
            await query.answer("Error playing memo", show_alert=True)
            return

        # Get memo date for display
        memo_date = ""
        memos = get_user_memos(user_id)
        for memo in memos:
            if memo['id'] == memo_id:
                memo_date = memo['date'].split()[0] if ' ' in memo['date'] else memo['date']
                break

        # Send a new message with the options menu
        options_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔊 Memo #{memo_id} ({memo_date})\n\n"
                 "What would you like to do with this memo?",
            parse_mode='HTML',
            reply_markup=get_memo_options_keyboard(memo_id)
        )
        
        # Store the options message ID
        if user_id not in user_last_messages:
            user_last_messages[user_id] = []
        user_last_messages[user_id].append(options_message.message_id)

        # Delete the original memo list message to keep the chat clean
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            # Remove from stored messages if it was there
            if user_id in user_last_messages and message_id in user_last_messages[user_id]:
                user_last_messages[user_id].remove(message_id)
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            # If deletion fails, it's not critical

    async def delete_memo_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle deleting a memo"""
        user_id = query.from_user.id
        
        # Extract memo ID from callback data
        try:
            memo_id = int(query.data.replace("delete_", ""))
        except ValueError:
            await query.answer("Invalid memo ID")
            return
        
        # Delete the memo
        if delete_memo(memo_id, user_id):
            await query.answer(f"Memo #{memo_id} deleted")
            # Go back to memos list
            await self.my_memos_handler(query, context)
        else:
            await query.answer("Failed to delete memo", show_alert=True)

    async def help_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Help button press"""
        help_text = (
            "🤖 <b>VaultBot Help</b>\n\n"
            "• <b>🎤 New Memo</b>: Record a new voice memo\n"
            "• <b>📋 My Memos</b>: View your saved memos\n"
            "• <b>🔐 Lock Vault</b>: Lock your vault for security\n\n"
            "Your data is encrypted and secure. Need more help?"
        )
        await query.edit_message_text(
            help_text, 
            parse_mode='HTML',
            reply_markup=get_help_inline_keyboard()
        )

    async def lock_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Lock the vault"""
        # Clear authentication state
        context.user_data['authenticated'] = False
        context.user_data['state'] = None
        
        # Remove user from activity tracking
        user_id = query.from_user.id
        if user_id in user_activity:
            del user_activity[user_id]
        
        # Clean up old messages
        await cleanup_old_messages(context, user_id, query.message.chat_id)
        
        await query.edit_message_text(
            "🔒 Vault locked.\n\n"
            "Click the button below to unlock when you're ready.",
            parse_mode='HTML',
            reply_markup=get_auth_inline_keyboard()
        )
    
    async def back_to_menu_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Back to Menu button press"""
        await query.edit_message_text(
            "What would you like to do?",
            parse_mode='HTML',
            reply_markup=get_main_menu_inline_keyboard()
        )
        
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
        logger.error(f"Failed to start bot: {e}")