# 🚀 Telegram VPN Subscription Bot

Полнофункциональный Telegram-бот для продажи подписок на VPN. Проект оптимизирован для работы на слабых VPS (от 1 ГБ ОЗУ) и включает в себя автоматическую оплату через множество шлюзов и управление пользователями в панели RemnaWave.

---

## ✨ Основные возможности

- **🖼️ Система баннеров**: Каждое сообщение (Главное меню, Профиль, Тарифы) сопровождается красивым изображением для лучшего UX.
- **🧭 Full Inline UI**: Навигация как в приложении: только `InlineKeyboard`, переходы через `callback_data`, редактирование одного сообщения.
- **💳 Автоматическая оплата**: 
  - **CryptoBot**: USDT, TON, BTC и др.
  - **FreeKassa**: СБП, Карты, Электронные кошельки.
  - **CryptoMus**: Криптовалюты с поддержкой вебхуков.
  - **Telegram Stars**: Внутренняя валюта Telegram.
  - **TON Connect**: Прямые платежи в сети TON с проверкой по комментарию.
- **🔑 Управление VPN**: Автоматическое создание пользователей и генерация ключей в панели RemnaWave.
- **👥 Реферальная система**: Система приглашений с бонусами на баланс пользователя.
- **🐳 Docker Ready**: Быстрое развертывание одной командой.

---

## ⚙️ Настройка окружения (.env)

Создайте файл `.env` на основе `.env.example`. Ниже приведено подробное описание каждой переменной:

### 🤖 Telegram Бот
- `BOT_TOKEN`: Токен вашего бота от [@BotFather](https://t.me/BotFather).
- `ADMIN_IDS`: ID получателей сервисных уведомлений через запятую.

### 🔑 VPN Панель (RemnaWave)
- `REMNAWAVE_API_URL`: URL вашей панели (например, `https://vpn.example.com/api`).
- `REMNAWAVE_API_KEY`: API ключ (Настройки -> API Keys).
- `REMNAWAVE_COOKIE`: Cookie авторизованной сессии.
- `SUB_DOMAIN`: Домен для ссылок подписки (например, `https://sub.example.com`).
- `REMNAWAVE_DEFAULT_SQUAD_UUID`: ID группы (Squad), в которую будут добавляться новые пользователи.

### 💳 Платежные шлюзы

#### 1. FreeKassa (СБП / Карты)
1. Зарегистрируйтесь на [FreeKassa](https://freekassa.ru/).
2. Создайте магазин и получите `Merchant ID`, `Secret 1` и `Secret 2`.
3. В настройках магазина укажите URL для оповещений: `https://your-domain.com/api/v1/payments/freekassa/webhook`.
4. Заполните в `.env`:
   - `FREEKASSA_MERCHANT_ID`
   - `FREEKASSA_SECRET_1`
   - `FREEKASSA_SECRET_2`

#### 2. CryptoBot
1. Получите токен в [@CryptoPay_bot](https://t.me/CryptoPay_bot).
2. Укажите `CRYPTOBOT_TOKEN` в `.env`.
3. URL для вебхуков: `https://your-domain.com/api/v1/payments/cryptobot/webhook`.

#### 3. CryptoMus
1. Получите API Key и Merchant ID на [cryptomus.com](https://cryptomus.com/).
2. Заполните `CRYPTOMUS_API_KEY` и `CRYPTOMUS_MERCHANT_ID` в `.env`.
3. URL для вебхуков: `https://your-domain.com/api/v1/payments/cryptomus/webhook`.

#### 4. TON Connect (Direct)
1. Укажите ваш адрес кошелька в `TON_WALLET_ADDRESS`.
2. Бот генерирует deep link для оплаты с обязательным комментарием (ID платежа).
3. После оплаты пользователь нажимает "Проверить", и система проверяет транзакцию.

#### 5. Telegram Stars
1. Настраивается через @BotFather -> Bot Settings -> Payments.
2. `STARS_CONVERSION_RATE` в `.env` (например, 50 звезд за 1 USD).

---

## 🚀 Быстрый старт (Docker)

1. **Клонируйте репозиторий**:
   ```bash
   git clone https://github.com/your-username/tg-vpn-bot.git
   cd tg-vpn-bot
   ```

2. **Настройте конфиг**:
   ```bash
   cp .env.example .env
   # Отредактируйте .env, указав ваши ключи и домены
   nano .env
   ```

3. **Запустите проект**:
   ```bash
   docker-compose up -d --build
   ```

---

## 📂 Структура проекта

- `backend/`: FastAPI сервер, обработка платежей и фоновые задачи.
- `bot/`: Логика Telegram бота на aiogram 3.
- `db/`: Инициализация и миграции БД.
- `data/`: Папка для SQLite базы данных (создается автоматически).

---

## 🛡️ Безопасность и бэкапы

- **SSL**: Для работы вебхуков обязательно используйте обратный прокси (Nginx/Traefik) с SSL (HTTPS).
- **Бэкап**: Регулярно копируйте файл `data/app.db`.
- **Логи**: Просмотр логов: `docker-compose logs -f`.

---

## 📄 Лицензия
MIT
