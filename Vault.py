import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
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

# Main menu keyboard
def get_main_menu_keyboard():
    return ReplyKeyboardMarkup([
        ['🎤 New Memo', '📋 My Memos'],
        ['🔐 Lock']
    ], resize_keyboard=True, one_time_keyboard=False)

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
        # Conversation handler for registration and login
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                AWAITING_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_new_password)
                ],
                AWAITING_LOGIN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_login_password)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_command)]
        )
        
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("lock", self.lock_command))
        
        # Add handlers for menu options
        self.application.add_handler(MessageHandler(filters.Regex('^🎤 New Memo$'), self.new_memo_handler))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 My Memos$'), self.my_memos_handler))
        self.application.add_handler(MessageHandler(filters.Regex('^🔐 Lock$'), self.lock_command))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Send a welcome message and check if user needs to set password or login"""
        user_id = update.effective_user.id
        
        if not user_exists(user_id):
            # New user - prompt for password setup
            await update.message.reply_text(
                "🔒 Welcome to VaultBot! 🔒\n\n"
                "Your secure, voice-based journal.\n\n"
                "📝 Please set your master password:",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_PASSWORD
        else:
            # Existing user - prompt for login
            await update.message.reply_text(
                "🔒 Vault is locked.\n\n"
                "Please enter your master password to unlock:",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_LOGIN

    async def handle_new_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the new master password input"""
        user_id = update.effective_user.id
        password = update.message.text
        
        # Validate password strength
        if len(password) < 6:
            await update.message.reply_text(
                "❌ Password must be at least 6 characters long.\n"
                "Please try again:",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_PASSWORD
        
        # Set the master password
        set_master_password(user_id, password)
        
        # Show main menu
        await update.message.reply_text(
            "✅ Master password set successfully!\n\n"
            "🔓 Your vault is now secured and ready to use.",
            parse_mode='HTML'
        )
        
        await update.message.reply_text(
            "What would you like to do?",
            reply_markup=get_main_menu_keyboard()
        )
        
        return ConversationHandler.END

    async def handle_login_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle login password input"""
        user_id = update.effective_user.id
        password = update.message.text
        
        # Verify the password
        if verify_master_password(user_id, password):
            # Show main menu
            await update.message.reply_text(
                "✅ Access granted!\n\n"
                "🔓 Your vault is now unlocked.",
                parse_mode='HTML'
            )
            
            await update.message.reply_text(
                "What would you like to do?",
                reply_markup=get_main_menu_keyboard()
            )
            
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Incorrect password.\n\n"
                "Please try again:",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_LOGIN

    async def lock_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Lock the vault and remove the keyboard"""
        await update.message.reply_text(
            "🔒 Vault locked.\n\n"
            "Use /start to unlock again.",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )

    async def new_memo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle New Memo button press"""
        await update.message.reply_text(
            "🎤 Ready to record your memo!\n\n"
            "Please send a voice message or type your memo.",
            parse_mode='HTML'
        )
        # Here you would set up state to handle the actual memo creation

    async def my_memos_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle My Memos button press"""
        await update.message.reply_text(
            "📋 Your memos:\n\n"
            "• Memo 1 (2023-10-15)\n"
            "• Memo 2 (2023-10-14)\n"
            "• Memo 3 (2023-10-13)\n\n"
            "Select a memo to view or listen to it.",
            parse_mode='HTML'
        )
        # Here you would fetch and display actual memos from storage

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the current operation"""
        await update.message.reply_text(
            "Operation cancelled.",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a help message"""
        help_text = (
            "🤖 <b>VaultBot Help</b>\n\n"
            "• Use /start to begin or access your vault\n"
            "• Use the menu buttons to navigate\n"
            "• Use /lock to secure your vault\n"
            "• Your data is encrypted and secure\n\n"
            "Need more help? Contact support@vaultbot.com"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
        
    def run(self):
        """Start the bot and initialize database"""
        init_db()  # Initialize database
        logger.info("Starting VaultBot...")
        self.application.run_polling()

if __name__ == '__main__':
    try:
        bot = VaultBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")