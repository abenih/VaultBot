import os
import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from database import init_db, user_exists, set_master_password, verify_master_password

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

class VaultBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("No BOT_TOKEN found in environment variables")
            raise ValueError("Bot token not found in environment variables")
            
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        
    def setup_handlers(self):
        """Set up all message handlers"""
        # Add handler for /start command
        self.application.add_handler(CommandHandler("start", self.start_command_handler))
        
        # Add handler for inline button callbacks
        self.application.add_handler(CallbackQueryHandler(self.inline_button_handler))
        
        # Add handler for text messages (for password input)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input)
        )
        
    async def start_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        # Clear any existing state
        context.user_data.clear()
        
        # Show welcome message
        await self.show_welcome_message(update, context)
    
    async def show_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show welcome message with start button"""
        welcome_text = (
            "🔒 Welcome to VaultBot! 🔒\n\n"
            "Your secure, voice-based journal.\n\n"
            "Click the button below to get started:"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=get_start_inline_keyboard()
        )
    
    async def inline_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
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
            await update.message.reply_text(
                "❌ Password must be at least 6 characters long.\n"
                "Please try again:",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        # Set the master password
        if set_master_password(user_id, password):
            # Show main menu with inline keyboard
            await update.message.reply_text(
                "✅ Master password set successfully!\n\n"
                "🔓 Your vault is now secured and ready to use.\n\n"
                "What would you like to do?",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            
            # Clear state and mark as authenticated
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            await update.message.reply_text(
                "❌ Failed to set password. Please try again:",
                parse_mode='HTML'
            )
    
    async def handle_login_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, password: str) -> None:
        """Handle login password input"""
        user_id = update.effective_user.id
        
        # Verify the password
        if verify_master_password(user_id, password):
            # Show main menu with inline keyboard
            await update.message.reply_text(
                "✅ Access granted!\n\n"
                "🔓 Your vault is now unlocked.\n\n"
                "What would you like to do?",
                parse_mode='HTML',
                reply_markup=get_main_menu_inline_keyboard()
            )
            
            # Clear state and mark as authenticated
            context.user_data['state'] = None
            context.user_data['authenticated'] = True
        else:
            await update.message.reply_text(
                "❌ Incorrect password.\n\n"
                "Please try again:",
                parse_mode='HTML',
                reply_markup=get_auth_inline_keyboard()
            )

    async def lock_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Lock the vault"""
        # Clear authentication state
        context.user_data['authenticated'] = False
        
        await query.edit_message_text(
            "🔒 Vault locked.\n\n"
            "Click the button below to unlock when you're ready.",
            parse_mode='HTML',
            reply_markup=get_auth_inline_keyboard()
        )

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
            
        await query.edit_message_text(
            "🎤 Ready to record your memo!\n\n"
            "Please send a voice message or type your memo.",
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
            
        await query.edit_message_text(
            "📋 Your memos:\n\n"
            "• Memo 1 (2023-10-15)\n"
            "• Memo 2 (2023-10-14)\n"
            "• Memo 3 (2023-10-13)\n\n"
            "Select a memo to view or listen to it.",
            parse_mode='HTML'
        )

    async def help_handler(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Help button press"""
        help_text = (
            "🤖 <b>VaultBot Help</b>\n\n"
            "• <b>🎤 New Memo</b>: Record a new voice or text memo\n"
            "• <b>📋 My Memos</b>: View your saved memos\n"
            "• <b>🔐 Lock Vault</b>: Lock your vault for security\n\n"
            "Your data is encrypted and secure. Need more help?"
        )
        await query.edit_message_text(
            help_text, 
            parse_mode='HTML',
            reply_markup=get_help_inline_keyboard()
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