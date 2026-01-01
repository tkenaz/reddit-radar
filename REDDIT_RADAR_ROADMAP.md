# Reddit Radar — Open Source Roadmap

**Цель:** Превратить наш internal reddit-mcp в публичный open source продукт для lead generation.

**Вдохновение:** Вирусный пост (2500 комментов, 32 репоста) про Reddit monitoring систему.

**Репо:** `kenaz-gmbh/reddit-radar`

---

## Phase 0: Подготовка (перед форком)

### 0.1 Security Cleanup
- [x] ~~Убрать хардкодные Telegram credentials~~ — N/A, новый проект без legacy кода
- [x] `.env` в .gitignore ✓
- [x] Kenaz-специфичные данные вынесены в config/keywords.yaml (gitignored)
- [x] Credentials через environment variables ✓

### 0.2 Repo Structure
```
reddit-radar/
├── README.md                    # Новый, для публики
├── LICENSE                      # MIT
├── .env.example                 # Все переменные с комментариями
├── config/
│   ├── keywords.yaml.example    # Generic пример
│   └── keywords.yaml            # .gitignore'd
├── src/
│   ├── scanner.py               # Daily scan (переименовать)
│   ├── monitor.py               # Engagement monitoring
│   ├── classifier.py            # NEW: AI intent classification
│   ├── notifier.py              # NEW: Unified notifications (Telegram/Slack/Email)
│   └── reddit_client.py         # Существующий
├── examples/
│   ├── saas_keywords.yaml       # Для SaaS бизнесов
│   ├── agency_keywords.yaml     # Для агентств
│   └── devtools_keywords.yaml   # Для dev tools
├── docs/
│   ├── SETUP.md                 # Детальная установка
│   ├── REDDIT_API.md            # Как получить credentials
│   └── NOTIFICATIONS.md         # Настройка уведомлений
└── scripts/
    ├── setup.sh                 # Автоустановка
    └── cron_setup.sh            # Настройка cron
```

---

## Phase 1: Core Refactoring ✅ DONE

### 1.1 Configuration System ✅
- [x] Создан `src/config.py` с dataclass моделями (RedditConfig, TelegramConfig, SlackConfig, EmailConfig, AIConfig, DatabaseConfig)
- [x] Все env vars через централизованный Settings класс
- [x] Валидация при старте с понятными ошибками
- [x] Graceful errors для missing credentials

```python
# Пример структуры
class Settings(BaseSettings):
    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str

    # Notifications (все опциональные)
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]
    slack_webhook_url: Optional[str]
    email_smtp_host: Optional[str]

    # AI (для классификации)
    anthropic_api_key: Optional[str]
    openai_api_key: Optional[str]

    class Config:
        env_file = ".env"
```

### 1.2 Unified Notifier ✅
- [x] Абстрактный интерфейс `BaseNotifier` с методами `send()` и `is_configured()`
- [x] `TelegramNotifier` с Markdown и priority emoji
- [x] `SlackNotifier` с Slack blocks
- [x] `EmailNotifier` через SMTP
- [x] `ConsoleNotifier` для тестов/дебага
- [x] `MultiNotifier` для отправки во все каналы
- [x] `get_notifier()` автовыбор по доступным credentials

```python
# Пример использования
notifier = get_notifier()  # Автоматически выбирает по .env
notifier.send("🔥 Hot lead detected!", priority="high")
```

---

## Phase 2: AI Intent Classification ✅ DONE (KILLER FEATURE)

### 2.1 Classifier Design ✅
- [x] Создан `src/classifier.py`
- [x] Поддержка Claude (Haiku по дефолту — дёшево!)
- [x] Fallback на rule-based если нет API key

### 2.2 Intent Categories ✅
```python
class Intent(Enum):
    HOT_LEAD = "hot_lead"           # Actively looking for solution/tool
    COMPETITOR = "competitor"        # Showcasing their own solution
    CONTENT_IDEA = "content_idea"    # Asking question (content opportunity)
    PARTNERSHIP = "partnership"      # Looking for contractor/agency/partner
    NOISE = "noise"                  # Not relevant for business
```

### 2.3 Classification Prompt ✅
Реализовано в `CLASSIFICATION_PROMPT` с JSON output

### 2.4 Smart Scoring ✅
- [x] `score_post()` комбинирует Reddit score + AI intent + subreddit priority
- [x] Intent boost: HOT_LEAD 2x, PARTNERSHIP 1.5x, CONTENT_IDEA 1.2x
- [x] Configurable subreddit weights через `subreddit_preferences`
- [x] Сортировка по score, top N в notification

---

## Phase 3: Knowledge Base Integration ✅ DONE

### 3.1 Company Profile ✅
- [x] `config/company.yaml` — полный профиль Kenaz с services, pricing, differentiators
- [x] Keyword matching для каждого сервиса
- [x] Red flags для фильтрации

### 3.2 Response Generation ✅
- [x] `config/system_prompt.yaml` — промпт с Marina's voice и style examples
- [x] `src/responder.py` — генерация через Opus 4.5
- [x] Intent-specific и subreddit-specific adjustments
- [x] Draft mode — человек всегда ревьюит перед постингом

---

## Phase 4: Nice-to-Have (v1.1+)

### 4.1 Response Generation
- [ ] AI-generated draft responses
- [ ] Human-in-the-loop approval
- [ ] "Reply" button в Telegram уведомлении

### 4.2 Analytics Dashboard
- [ ] Simple web UI (FastAPI + htmx?)
- [ ] Conversion tracking
- [ ] Historical trends

### 4.3 Multi-platform
- [ ] Hacker News monitoring
- [ ] Twitter/X mentions
- [ ] Discord servers

---

## Launch Checklist

### Pre-launch
- [x] README с quickstart инструкциями
- [x] .env.example с комментариями
- [x] Quickstart работает за < 5 минут
- [ ] GIF/video demo
- [ ] Тесты (хотя бы базовые)
- [ ] GitHub Actions для CI

### Launch Day
- [ ] Hacker News: "Show HN: Reddit Radar – Open source lead gen from Reddit"
- [ ] Reddit: r/SideProject, r/selfhosted, r/Entrepreneur
- [ ] LinkedIn: пост от Marina
- [ ] Twitter: thread

### Post-launch
- [ ] Мониторить issues
- [ ] Отвечать на комментарии (dogfooding!)
- [ ] Собирать фидбек для v1.1

---

## Effort Estimate

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 0 | Security cleanup | ✅ DONE |
| Phase 1 | Core refactoring | ✅ DONE |
| Phase 2 | AI Classification | ✅ DONE |
| Phase 3 | Knowledge base + Response Gen | ✅ DONE |
| Phase 4 | Nice-to-have | ⏳ TODO |
| **Full Feature Set** | Phases 0-3 | **✅ COMPLETE** |

---

## Open Questions

1. **Название:** `reddit-radar` или что-то более catchy?
2. **Лицензия:** MIT (максимум adoption) или Apache 2.0 (patent protection)?
3. **База данных:** SQLite для простоты или оставить PostgreSQL?
4. **Приоритет:** Сначала AI classification или сначала multi-notifier?

---

**Created:** 2025-12-29
**Updated:** 2025-12-29
**Author:** Claude & Marina
**Status:** MVP Complete (Phase 0-2) — ready for Phase 3 or launch prep
