# 🚀 Telegram VPN Subscription Bot

A production-ready Telegram VPN bot optimized for low-resource VPS (1GB RAM). Built with Python, Aiogram, FastAPI, and SQLite.

## 🧱 Project Goal
Provide a stable, lightweight, and easy-to-deploy system for managing VPN subscriptions via Telegram with automated payments and provisioning.

---

## ⚙️ Environment Variables (Configuration)

Before running the bot, you need to set up your `.env` file. See [.env.example](.env.example) for a template.

### 🤖 Telegram Bot
*   **`BOT_TOKEN`**: The unique token for your Telegram bot.
    *   **How to get**: Message [@BotFather](https://t.me/BotFather) on Telegram, create a new bot, and copy the API token.
*   **`ADMIN_IDS`**: Comma-separated list of Telegram User IDs who will have admin access.
    *   **How to get**: Use [@userinfobot](https://t.me/userinfobot) to find your ID.

### 🔑 VPN Integration (RemnaWave)
*   **`REMNAWAVE_API_URL`**: The base URL of your RemnaWave instance API.
    *   **Where to find**: Usually `https://your-panel-domain.com/api`.
*   **`REMNAWAVE_API_KEY`**: Your secret API key for RemnaWave.
    *   **How to get**: Go to your RemnaWave Panel -> Settings -> API Keys -> Create New Key.

### 💳 Payments (CryptoBot)
*   **`CRYPTOBOT_TOKEN`**: API token for CryptoBot payments.
    *   **How to get**: Message [@CryptoBot](https://t.me/CryptoBot), go to **Crypto Pay** -> **My Apps** -> **Create App**, then copy the **API Token**.
*   **`USE_WEBHOOK`**: Set to `True` to use webhooks (requires HTTPS) or `False` to use background polling (easier for local testing).
*   **`WEBHOOK_URL`**: Your public backend URL for CryptoBot webhooks.
    *   **Example**: `https://api.yourdomain.com/api/v1/payments/cryptobot/webhook`

### 💾 Database
*   **`DATABASE_URL`**: SQLAlchemy connection string for SQLite.
    *   **Format**: `sqlite+aiosqlite:///./app.db` (Default)

---

## 🛠️ Step-by-Step Setup

### 1. Prerequisites
*   A VPS with at least 1GB RAM.
*   [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

### 2. Installation
1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/tg-vpn-bot.git
    cd tg-vpn-bot
    ```

2.  **Configure Environment**:
    ```bash
    cp .env.example .env
    nano .env  # Fill in your variables
    ```

3.  **Run the Project**:
    ```bash
    docker-compose up -d --build
    ```

---

## 🌍 VPS Deployment Guide

### 1. Connect to your VPS
```bash
ssh root@your_vps_ip
```

### 2. Install Docker (One-liner for Ubuntu/Debian)
```bash
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
```

### 3. Deploy
Follow the **Installation** steps above. The `docker-compose.yml` is configured with `restart: always`, meaning your bot will automatically start if the server reboots or the app crashes.

---

## 💾 Backup Guide

Since we use SQLite, all your data is in a single file: `data/app.db`.

### How to Backup
You can simply copy the file even while the bot is running (thanks to WAL mode). If using Docker, the file is located inside the `sqlite_data` volume, but you can also find it in your project's `data/` folder if you mapped it.

### Automated Backups (Cron)
To backup your database every 6 hours, add this to your `crontab -e`:
```bash
0 */6 * * * cp /path/to/tg-vpn-bot/data/app.db /path/to/backups/app_$(date +\%Y\%m\%d_\%H\%M\%S).db
```

---

## 🔍 Troubleshooting

### 🛑 Bot not responding
1.  Check if containers are running: `docker-compose ps`
2.  Check logs: `docker-compose logs -f bot`
3.  Ensure `BOT_TOKEN` is correct.

### 🔒 Database is locked
This usually happens if multiple processes try to write to SQLite simultaneously. 
*   **Fix**: Our project uses **WAL Mode** and **Async** access to minimize this. If it persists, ensure you aren't running multiple instances of the backend.

### 💸 Payment not confirmed
*   If using **Webhooks**: Ensure your `WEBHOOK_URL` is correct, uses `https`, and is accessible from the internet.
*   If using **Polling**: Ensure `USE_WEBHOOK=False` in your `.env`.

---

## 🏗️ Architecture (Simplified)

```ascii
User -> Telegram Bot (Aiogram) -> Backend (FastAPI) -> SQLite
                                      |
                                      +-> RemnaWave (VPN)
                                      +-> CryptoBot (Payments)
```

## 🔐 Security
- No secrets stored in code (all in `.env`).
- Webhook signature validation.
- SQLite WAL mode for data integrity.
- Pydantic models for input validation.
