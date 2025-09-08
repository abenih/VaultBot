import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with HTML formatting and an inline start button when the /start command is issued."""
    # Create an inline keyboard with a "Start" button
    keyboard = [[InlineKeyboardButton("🚀 Start", callback_data='start_button')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Formatted welcome message using HTML
    welcome_text = (
        "🔒 <b>Welcome to VaultBot!</b> 🔒\n"
        "Your secure, voice-based journal. Press Start to begin."
    )
    
    # Send the message with HTML parse_mode and the inline keyboard
    await update.message.reply_text(
        text=welcome_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the callback from the inline button."""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query
    
    # Edit the message to remove the button and confirm initiation
    await query.edit_message_text(
        text="🔓 <b>VaultBot initiated!</b> 🔓\nLet's get started with your secure journal.",
        parse_mode='HTML'
    )
    
    # Here you can add further steps to guide the user, e.g., asking for voice input

def main() -> None:
    """Start the bot."""
    # Replace 'YOUR_BOT_TOKEN' with your actual bot token obtained from BotFather
    application = Application.builder().token("7526000908:AAE0IyU8TqGTqDADrnQ4pQMmajZsah50J7A").build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback, pattern='^start_button$'))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()