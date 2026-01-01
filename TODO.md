# Reddit Radar — TODO

**Testing period:** until January 12, 2025

---

## Pre-Production (Testing Phase)

### Style & Quality
- [ ] Fine-tune `config/system_prompt.yaml` based on generated drafts
- [ ] Review posted comments for tone/style consistency
- [ ] Adjust classification thresholds if too many false positives/negatives
- [ ] Test Edit flow more thoroughly

### Bug Fixes
- [ ] Fix 400 error on summary notification (message too long)
- [ ] Handle 409 Conflict gracefully (single bot instance check)
- [ ] Add retry logic for Reddit rate limits

### Testing
- [ ] Run for 2-3 days, collect feedback
- [ ] Check draft quality across different subreddits
- [ ] Verify cron runs reliably
- [ ] Test Skip button flow

---

## Production Deployment

### Infrastructure
- [ ] Set up approval_bot as systemd service (or launchd on macOS)
- [ ] Configure log rotation for `logs/scanner.log`
- [ ] Set up monitoring/alerting (optional)
- [ ] Consider moving SQLite to PostgreSQL for multi-user

### Security
- [ ] Audit all credentials in .env
- [ ] Ensure .env not in git (already done)
- [ ] Review Reddit API rate limits

### Documentation
- [ ] README.md — quickstart guide
- [ ] docs/SETUP.md — detailed installation
- [ ] docs/REDDIT_API.md — how to get credentials
- [ ] docs/TELEGRAM_BOT.md — bot setup instructions
- [ ] Add GIF/video demo

### Code Quality
- [ ] Add basic tests (pytest)
- [ ] GitHub Actions CI
- [ ] Type hints cleanup
- [ ] Docstrings for public functions

### Open Source Prep
- [ ] Remove Kenaz-specific data from examples
- [ ] Create generic `config/keywords.yaml.example`
- [ ] Add CONTRIBUTING.md
- [ ] Choose license (MIT recommended)

---

## Nice-to-Have (v1.1+)

- [ ] Web dashboard for analytics
- [ ] Slack integration for approval flow
- [ ] Multi-user support
- [ ] Hacker News monitoring
- [ ] Twitter/X mentions
- [ ] Response templates library
- [ ] A/B testing for response styles

---

## Current Status

| Component | Status |
|-----------|--------|
| Scanner | ✅ Working, cron every 4h |
| Classifier (Haiku) | ✅ Working |
| Responder (Opus 4.5) | ✅ Working |
| Telegram buttons | ✅ Working |
| Approval bot | ⚠️ Needs to run manually |
| Edit flow | ✅ Working |
| Post to Reddit | ✅ Working |

---

**Last updated:** 2025-01-01
