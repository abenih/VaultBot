import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback, pattern='^start_button$'))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a welcome message with HTML formatting and an inline start button."""
        keyboard = [[InlineKeyboardButton("🚀 Start Journaling", callback_data='start_button')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            "🔒 <b>Welcome to VaultBot!</b> 🔒\n\n"
            "Your secure, voice-based journal.\n\n"
            "• Record voice notes as journal entries\n"
            "• Your data is encrypted and secure\n"
            "• Access your entries anytime\n\n"
            "Press Start to begin your journaling journey."
        )
        
        await update.message.reply_text(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the callback from the inline button."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            text="🔓 <b>VaultBot initiated!</b> 🔓\n\n"
                 "Your journal is ready. You can now:\n\n"
                 "• Send voice messages to add entries\n"
                 "• Use /entries to view your past journals\n"
                 "• Use /help for assistance",
            parse_mode='HTML'
        )
        
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming voice messages."""
        voice = update.message.voice
        user = update.message.from_user
        
        # Create user directory if it doesn't exist
        user_dir = f"user_data/{user.id}"
        os.makedirs(user_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{user_dir}/voice_{timestamp}.ogg"
        
        # Download the voice message
        voice_file = await voice.get_file()
        await voice_file.download_to_drive(filename)
        
        # Confirm receipt
        await update.message.reply_text(
            text=f"✅ <b>Journal entry saved!</b>\n"
                 f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                 f"Duration: {voice.duration} seconds",
            parse_mode='HTML'
        )
        
        # Here you would typically:
        # 1. Store metadata in a database
        # 2. Process the voice file (transcription, etc.)
        logger.info(f"Voice message saved for user {user.id}: {filename}")
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a help message."""
        help_text = (
            "🤖 <b>VaultBot Help</b>\n\n"
            "• Just send a voice message to add a journal entry\n"
            "• Use /entries to list your past entries (coming soon)\n"
            "• Your data is private and secure\n\n"
            "Need more help? Contact support@vaultbot.com"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
        
    def run(self):
        """Start the bot."""
        logger.info("Starting VaultBot...")
        self.application.run_polling()

if __name__ == '__main__':
    try:
        bot = VaultBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")