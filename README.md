# 🚀 Telegram VPN Subscription Bot (SQLite Edition)

A production-ready Telegram VPN bot optimized for low-resource VPS (1GB RAM) using SQLite, RemnaWave API, and CryptoBot payments.

## 🧱 Architecture

```ascii
+-------------------+       +-------------------+       +-------------------+
|   Telegram User   | <---> |   Aiogram Bot     | <---> |   SQLite DB       |
+-------------------+       +-------------------+       |   (WAL Mode)      |
                                    ^                   +-------------------+
                                    |                           ^
                                    v                           |
+-------------------+       +-------------------+               |
|   CryptoBot Webhook| ---> |   FastAPI Backend | <-------------+
+-------------------+       +-------------------+               |
                                    ^                           |
                                    |                           |
                                    v                           |
                            +-------------------+               |
                            |   RemnaWave API   | <-------------+
                            +-------------------+
```

## ⚡ Key Features

- **SQLite Optimized**: Configured with WAL mode and `synchronous=NORMAL` for maximum performance on low-resource hardware.
- **Lightweight**: No Redis or Celery. Background tasks run directly in the FastAPI event loop.
- **VPN Provisioning**: Seamless integration with RemnaWave API for VLESS keys.
- **Payments**: Idempotent webhook processing for CryptoBot.
- **Referral System**: Built-in user rewards and referral link tracking.

## 🛠️ Tech Stack

- **Language**: Python 3.11+
- **Bot**: Aiogram 3.x
- **API**: FastAPI
- **Database**: SQLite with SQLAlchemy (Async)
- **Infrastructure**: Docker & Docker Compose

## 🚀 How to Run Locally

1.  **Clone the repository**:
    ```bash
    git clone <repo_url>
    cd <repo_name>
    ```

2.  **Configure environment**:
    ```bash
    cp .env.example .env
    # Fill in your BOT_TOKEN, CRYPTOBOT_TOKEN, etc.
    ```

3.  **Run with Docker**:
    ```bash
    docker-compose up --build
    ```

## 🌍 VPS Deployment (1GB RAM)

This system is specifically designed for 1GB RAM servers.

1.  **Install Docker and Docker Compose** on your VPS.
2.  **Transfer files** to the server.
3.  **Update `.env`** with production values (Webhook URLs, actual API keys).
4.  **Launch**: `docker-compose up -d`.

## 💾 SQLite Optimization & Limitations

### Optimization
- **WAL Mode**: Enabled for concurrent reads and writes.
- **Synchronous=NORMAL**: Reduced disk I/O while maintaining safety.
- **Connection Pooling**: Managed via `StaticPool` for stability.

### Limitations
- Not suitable for 10,000+ concurrent active users.
- Single-file database (backups are easy but must be handled carefully).

## 🛡️ Backup Strategy (MANDATORY)

Since SQLite is a single file (`app.db`), backups are simple but critical.

### How to Backup
1.  **Direct Copy**: Simply copy the `app.db` file while the application is running (WAL mode makes this safe).
2.  **VACUUM INTO**: Use `VACUUM INTO 'backup.db'` for a consistent snapshot.

### Backup Schedule
- **Frequency**: Every 6 hours recommended.
- **Retention**: Keep at least 7 days of backups.

### Example Cron Job
```bash
# Every 6 hours, copy the DB to a backup folder with a timestamp
0 */6 * * * cp /path/to/app.db /path/to/backups/app_$(date +\%Y\%m\%d_\%H\%M\%S).db
```

## 🔄 Migration to PostgreSQL

If you outgrow SQLite, the transition is straightforward:
1.  Update `DATABASE_URL` in `.env` to a PostgreSQL connection string.
2.  Install `asyncpg`.
3.  Run Alembic migrations to create the schema in Postgres.
4.  Use a tool like `pgloader` to migrate existing data.

## 🔐 Security
- Environment variables for all secrets.
- Webhook signature validation for payments.
- Input sanitization via Pydantic and SQLAlchemy.
