# Uptime Monitor

## Запуск (локально, с Docker)
1. Скопируйте `.env.example` в `.env` и заполните переменные.
2. Настройте `monitor/targets.yml` — укажите ваши сайты.
3. Запустите:

flowchart LR
  A[Checker service (Python)] --> B[SQLite (history)]
  A --> C[Notifier (Telegram, Email)]
  A --> D[Web dashboard (HTTP)]
  E[User / Ops] --> D
  C --> F[Telegram users]
  C --> G[Email recipients]
