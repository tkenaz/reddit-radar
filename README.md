# Reddit Radar

**Turn Reddit into your highest-intent lead generation channel.**

Reddit Radar monitors subreddits for people actively looking for solutions like yours, scores them by relevance, and sends you alerts via Telegram, Slack, or email.

## Why Reddit?

People don't pitch on Reddit — they ask for help. When someone posts "looking for a tool to automate X" or "need recommendations for Y", that's a high-intent lead actively searching for a solution.

Reddit Radar helps you:
- **Find leads** — People asking for exactly what you sell
- **Monitor competitors** — See what people say about alternatives
- **Generate content ideas** — Questions = blog post opportunities
- **Stay informed** — Track industry discussions

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/kenaz-gmbh/reddit-radar.git
cd reddit-radar
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get Reddit API credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app..."
3. Select **script** as the type
4. Set redirect URI to `http://localhost:8080`
5. Save your `client_id` and `secret`

### 3. Configure

```bash
cp .env.example .env
cp config/keywords.yaml.example config/keywords.yaml
```

Edit `.env` with your Reddit credentials and notification settings.
Edit `config/keywords.yaml` with your keywords and target subreddits.

### 4. Run

```bash
# Test run (prints to console)
python -m src.scanner --dry-run

# Production run (sends notifications)
python -m src.scanner
```

### 5. Schedule (optional)

Run every 4 hours via cron:

```bash
# Edit crontab
crontab -e

# Add this line (adjust path)
0 */4 * * * cd /path/to/reddit-radar && .venv/bin/python -m src.scanner
```

## Configuration

### Keywords (`config/keywords.yaml`)

Define what to search for:

```yaml
categories:
  hot_leads:
    name: "People Looking for Solutions"
    keywords:
      - "looking for tool"
      - "need software"
      - "recommendations for"
    subreddits:
      - "SaaS"
      - "startups"
      - "Entrepreneur"
    priority: high
```

### Notifications

Configure one or more notification channels in `.env`:

| Channel | Setup |
|---------|-------|
| **Telegram** | Create bot via @BotFather, get chat ID from @userinfobot |
| **Slack** | Create [incoming webhook](https://api.slack.com/messaging/webhooks) |
| **Email** | SMTP credentials (Gmail works with app passwords) |

## Features

### Current (v1.0)
- Multi-keyword, multi-subreddit search
- Relevance scoring based on engagement
- Telegram, Slack, and Email notifications
- Rate limiting (respects Reddit API limits)
- Dry-run mode for testing

### Planned (v1.1)
- AI-powered intent classification (hot lead vs. question vs. competitor)
- Response draft suggestions
- Engagement tracking over time
- Web dashboard

## Project Structure

```
reddit-radar/
├── src/
│   ├── config.py        # Centralized configuration
│   ├── reddit_client.py # Reddit API wrapper
│   ├── scanner.py       # Main scanning logic
│   └── notifier.py      # Notification system
├── config/
│   └── keywords.yaml    # Your search configuration
├── .env                 # Your credentials (git-ignored)
└── .env.example         # Template for credentials
```

## Best Practices

### Reddit Etiquette
- **Don't spam** — Provide genuine value when responding
- **9:1 rule** — 9 helpful comments for every 1 self-promotion
- **Read the room** — Each subreddit has its own culture
- **Be human** — People can smell marketing from miles away

### Effective Keywords
- **Intent signals**: "looking for", "need help with", "recommendations"
- **Pain points**: "frustrated with", "hate dealing with", "waste time on"
- **Comparison**: "alternative to [Competitor]", "vs", "better than"

## FAQ

**Q: Will I get banned for using this?**
A: Reddit Radar just searches and notifies — it doesn't post or comment automatically. You manually respond to leads. The built-in rate limiting respects Reddit's API limits.

**Q: How often should I scan?**
A: Every 4-6 hours is a good balance. More frequent = more API calls. Less frequent = might miss time-sensitive leads.

**Q: Can I use this for multiple products/clients?**
A: Yes! Create separate `keywords.yaml` files and run with `--config path/to/keywords.yaml`.

## Contributing

PRs welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Submit a PR with clear description

## License

MIT License — see [LICENSE](LICENSE) file.

---

Built with love by [Kenaz GmbH](https://kenaz.io) — Custom AI Agents & Semantic Engineering
