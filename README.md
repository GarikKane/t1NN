flowchart LR
  A[Checker service (Python)] --> B[SQLite (history)]
  A --> C[Notifier (Telegram, Email)]
  A --> D[Web dashboard (HTTP)]
  E[User / Ops] --> D
  C --> F[Telegram users]
  C --> G[Email recipients]
