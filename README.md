VaultBot 🔒
A secure, voice-based journaling Telegram bot with AI-assisted transcription and summarization.

Overview
VaultBot is designed to provide a secure and intuitive way to record, store, and manage your voice memos. It leverages AI-powered features (via LemonFox.ai) for transcription and summarization of your voice recordings. The bot ensures data security by encrypting and securely storing your entries.

Features
Voice Message Journal Entries: Record and save your thoughts as voice memos.
Secure Storage: Your memos are stored securely, ensuring privacy and confidentiality.
AI-Assisted Transcription: Convert your voice memos into text using advanced speech-to-text technology.
Memo Summarization: Generate concise summaries of your voice memos using AI.
User Authentication: Protect your vault with a master password.
Inactivity Lock: Automatically locks the vault after 5 minutes of inactivity for added security.
Intuitive Interface: Easy-to-use inline keyboards for navigation.
Help and Support: Built-in help menu and contact support options.
Setup Instructions
Prerequisites
Python 3.8+
A Telegram Bot Token
An API key from LemonFox.ai for AI features (optional but recommended)
Steps
Clone the Repository
bash


1
2
git clone https://github.com/abenih/VaultBot.git
cd VaultBot
Create a Virtual Environment
bash


1
2
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
Install Dependencies
bash


1
pip install -r requirements.txt
Configure Environment Variables
Create a .env file in the root directory and add the following:


1 BOT_TOKEN=your_telegram_bot_token_here
2 LEMONFOX_API_KEY=your_lemonfox_api_key_here

Initialize the Database
Run the bot once to automatically initialize the database. The bot will create the necessary tables on its first run.
Start the Bot
bash


1
python main.py
Usage
Getting Started
Add the bot on Telegram.
Send /start to begin.
Follow the on-screen instructions to set up your vault or unlock it if you already have one.
Main Menu Options
🎤 New Memo: Record a new voice memo.
📋 My Memos: View and manage your saved memos.
🔒 Lock Vault: Lock your vault for enhanced security.
📝 Transcribe: Convert a voice memo into text.
✨ Summarize: Generate a summary of a voice memo.
❓ Help: Access help documentation and contact support.
Recording a Memo
Select "🎤 New Memo" from the main menu.
Send a voice message to record your memo.
The bot will confirm that your memo has been saved securely.
Managing Memos
View Memos: Select "📋 My Memos" to see a list of your saved memos.
Listen to a Memo: Tap on a memo to play it back.
Transcribe: Convert a memo into text using AI.
Summarize: Generate a concise summary of a memo.
Delete: Remove a memo from your vault.
Security Features
Master Password: Secure your vault with a password to prevent unauthorized access.
Inactivity Lock: The vault automatically locks after 5 minutes of inactivity to protect your data.
Contact Support
If you encounter any issues or need assistance, use the "📞 Contact Support" option in the help menu to reach out via Telegram at @abeni_h .

Technical Details
Dependencies
python-telegram-bot: For handling Telegram interactions.
openai: For integrating with LemonFox.ai's AI services.
sqlite3: For local database storage of user data and memos.
dotenv: For managing environment variables securely.
Database Schema
The bot uses an SQLite database to store user information, memos, transcriptions, and summaries. The schema includes tables for users, memos, and associated metadata.

AI Integration
Transcription: Uses LemonFox.ai's Whisper model for converting voice messages to text.
Summarization: Employs LemonFox.ai's LLM (Language Model) for generating summaries of transcribed text.
Security Measures
Data Encryption: All sensitive data is encrypted before storage.
Password Protection: User vaults are protected by a master password.
Inactivity Timeout: Automatically locks the vault after 5 minutes of inactivity to prevent unauthorized access.
Contributing
If you'd like to contribute to VaultBot, feel free to fork the repository and submit pull requests. Contributions such as bug fixes, feature enhancements, or improvements to the documentation are welcome!


Contact
For inquiries or feedback, reach out to the developer via Telegram at @abeni_h .

