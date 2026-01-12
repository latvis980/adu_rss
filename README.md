# 🏛️ ArchNews Monitor

A simple news monitoring bot that collects architecture news from ArchDaily, generates AI summaries, and sends them to a Telegram channel.

## Features

- 📡 Fetches latest articles from ArchDaily RSS feed
- 🤖 AI-powered summaries using Claude via LangChain
- 📱 Sends formatted digest to Telegram channel
- 📁 Prompts stored in separate files for easy editing

## Project Structure

```
archnews/
├── monitor.py          # Main script
├── prompts/
│   └── summarize.txt   # AI prompt for summarization
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── README.md
```

## Setup

### 1. Clone and install dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Create Telegram Bot

1. Open Telegram and find [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow instructions
3. Copy the bot token

### 3. Set up Telegram Channel

1. Create a channel (or use existing one)
2. Add your bot as administrator with "Post messages" permission
3. Get channel ID:
   - For public channels: use `@channelname`
   - For private channels: forward a message from channel to [@userinfobot](https://t.me/userinfobot)

### 4. Configure environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your values
nano .env  # or use any editor
```

Required variables:
- `TELEGRAM_BOT_TOKEN` - from BotFather
- `TELEGRAM_CHANNEL_ID` - your channel (@name or ID)
- `ANTHROPIC_API_KEY` - from [Anthropic Console](https://console.anthropic.com/)

### 5. Run

```bash
python monitor.py
```

## Optional: Enable LangSmith Tracing

To monitor AI calls with LangSmith:

1. Get API key from [LangSmith](https://smith.langchain.com/)
2. Add to `.env`:
   ```
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=your_key
   LANGCHAIN_PROJECT=archnews-monitor
   ```

## Deployment on Railway

1. Create new project on [Railway](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables in Railway dashboard
4. Set up cron job for daily execution (e.g., `0 8 * * *` for 8 AM daily)

## Next Steps

- [ ] Add Cloudflare R2 storage for article JSON files
- [ ] Implement deduplication (GUID tracking)
- [ ] Add more news sources (Dezeen, Designboom, etc.)
- [ ] Create editorial digest compilation
- [ ] Build PWA frontend

## License

MIT
