# 🚀 Telegram VPN Subscription Bot

Полнофункциональный Telegram-бот для продажи подписок на VPN. Проект оптимизирован для работы на слабых VPS (от 1 ГБ ОЗУ) и включает в себя автоматическую оплату через CryptoBot и управление пользователями в панели RemnaWave.

---

## ✨ Основные возможности

- **🖼️ Система баннеров**: Каждое сообщение (Главное меню, Профиль, Тарифы) сопровождается красивым изображением для лучшего UX.
- **🧭 Full Inline UI**: Навигация как в приложении: только `InlineKeyboard`, переходы через `callback_data`, редактирование одного сообщения.
- **💳 Автоматическая оплата**: Интеграция с [CryptoBot](https://t.me/CryptoBot) (поддержка USDT, TON, BTC и др.).
- **🔑 Управление VPN**: Автоматическое создание пользователей и генерация ключей в панели RemnaWave.
- **👥 Реферальная система**: Система приглашений с бонусами на баланс пользователя.
- **📱 Удобный профиль**: Отображение статуса подписки, остатка дней и VPN-ключа в одно нажатие.
- **🐳 Docker Ready**: Быстрое развертывание одной командой.

---

## 🛠️ Технологический стек

- **Язык**: Python 3.10+
- **Бот**: [Aiogram 3.x](https://docs.aiogram.dev/) (асинхронный фреймворк)
- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (для вебхуков и API)
- **База данных**: SQLite + [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (асинхронный режим)
- **HTTP Клиент**: [httpx](https://www.python-httpx.org/) и [curl_cffi](https://github.com/yifeikong/curl_cffi) (для имитации браузера при запросах к панели)
- **Развертывание**: Docker & Docker Compose

---

## ⚙️ Настройка окружения (.env)

Создайте файл `.env` на основе `.env.example`. Ниже приведено подробное описание каждой переменной:

### 🤖 Telegram Бот
- `BOT_TOKEN`: Токен вашего бота от [@BotFather](https://t.me/BotFather).
- `ADMIN_IDS`: ID получателей сервисных уведомлений через запятую (узнать свой ID можно в [@userinfobot](https://t.me/userinfobot)).

### 🔑 VPN Панель (RemnaWave)
- `REMNAWAVE_API_URL`: URL вашей панели (например, `https://vpn.example.com/api`).
- `REMNAWAVE_API_KEY`: API ключ (Настройки -> API Keys).
- `REMNAWAVE_COOKIE`: Cookie авторизованной сессии (необходимо для некоторых функций API).
- `SUB_DOMAIN`: Домен для ссылок подписки (например, `https://sub.example.com`).
- `REMNAWAVE_DEFAULT_SQUAD_UUID`: ID группы (Squad), в которую будут добавляться новые пользователи.

### 💳 Платежи
- **CryptoBot**: USDT, TON, BTC и др. через [@CryptoBot](https://t.me/CryptoBot).
- **Telegram Stars**: Оплата внутренними звездами Telegram (удобно для iOS/Android).
- **TON (Direct)**: Прямые платежи на ваш TON кошелек (ручная проверка перевода по комментарию).

### ⚙️ Настройка новых методов оплаты

#### ⭐️ Telegram Stars
1. Не требует специального токена.
2. Настройте `STARS_CONVERSION_RATE` в `.env` (по умолчанию 50 звезд = 1 USD).
3. Убедитесь, что ваш бот поддерживает платежи (настраивается через @BotFather -> Bot Settings -> Payments).

#### 💎 TON (Direct/TonConnect)
1. Укажите ваш адрес кошелька в `TON_WALLET_ADDRESS` в `.env`.
2. Укажите рыночный ориентир `TON_PRICE_USD` (используется для формирования суммы в deep link).
3. Бот формирует Tonkeeper ссылку формата `https://app.tonkeeper.com/transfer/{WALLET}?amount=...&text=...`.
4. Текущая реализация: ручная проверка платежа и активация подписки после подтверждения.
5. `TONCONNECT_MANIFEST_URL` добавлен в конфиг как подготовка к полной TonConnect-интеграции.

### 🔧 Переменные оплаты в `.env`
- `CRYPTOBOT_TOKEN`: API-токен из CryptoBot.
- `USE_WEBHOOK`: `True` для webhook-режима, `False` для polling.
- `WEBHOOK_URL`: публичный URL webhook-эндпоинта бэкенда.
- `STARS_CONVERSION_RATE`: курс пересчета доллара в звезды Telegram.
- `TON_WALLET_ADDRESS`: адрес TON-кошелька для прямых платежей.
- `TON_PRICE_USD`: ориентир цены TON в USD для расчета суммы в deep link.
- `TONCONNECT_MANIFEST_URL`: ссылка на manifest (резерв под TonConnect).

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
   nano .env
   ```

3. **Запустите проект**:
   ```bash
   docker-compose up -d --build
   ```

Бот и бекенд запустятся автоматически. База данных будет создана в директории `data/`.

---

## 👨‍💻 Локальная разработка (без Docker)

Если вы хотите запустить проект локально для разработки:

1. **Создайте виртуальное окружение**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Для Linux/macOS
   # venv\Scripts\activate  # Для Windows
   ```

2. **Установите зависимости**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Запустите бекенд**:
   ```bash
   python -m backend.main
   ```

4. **Запустите бота (в другом терминале)**:
   ```bash
   python -m bot.main
   ```

---

## 📂 Структура проекта

```text
├── backend/                # Логика сервера и API
│   ├── core/               # Настройки и конфиг
│   ├── models/             # Модели SQLAlchemy
│   ├── services/           # Бизнес-логика (VPN, Платежи, Задачи)
│   └── main.py             # Точка входа FastAPI
├── bot/                    # Telegram бот
│   ├── handlers/           # Обработчики команд и сообщений
│   ├── keyboards/          # Инлайн и реплай клавиатуры
│   ├── services/           # Рендеринг и вспомогательные функции
│   └── main.py             # Точка входа бота
├── db/                     # Настройка БД и миграции
├── data/                   # Файлы базы данных (создается автоматически)
├── docker-compose.yml      # Конфигурация Docker
└── requirements.txt        # Зависимости Python
```

---

## 🛡️ Безопасность и бэкапы

- **База данных**: Проект использует SQLite. Все данные хранятся в одном файле `data/app.db`.
- **Бэкап**: Достаточно просто скопировать файл `app.db`. Рекомендуется настроить cron-задачу для копирования этого файла раз в сутки.
- **SSL**: Для работы вебхуков CryptoBot обязательно используйте обратный прокси (например, Nginx) с настроенным SSL (Certbot/Let's Encrypt).

---

## ❓ FAQ

**В: Пользователь оплатил, но подписка не появилась.**
О: Проверьте логи бекенда (`docker logs vpn_backend`). Скорее всего, возникла ошибка при запросе к панели RemnaWave (проверьте `REMNAWAVE_COOKIE` и `API_KEY`).

**В: Как изменить текст приветствия или баннер?**
О: Только через код/БД. Бот-админка удалена. Меняйте значения экранов в [init_db.py](file:///Users/matvei/Documents/trae_projects/tglioshabotvpn/backend/services/init_db.py) или напрямую в таблице `screens`.

---

## 📄 Лицензия

Проект распространяется под лицензией MIT. Вы можете свободно использовать, изменять и распространять его.
