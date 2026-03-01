# MathBot

A Telegram-based competitive math game for Hong Kong primary school students (P5/P6). Runs a nightly 3-round session combining live group battles, solo accuracy challenges, and peer-to-peer duels — all inside Telegram via inline keyboards. Progress is tracked via XP, rank tiers, coins, streaks, and badges. A coin-based shop provides strategic power-ups.

> All in-game messages are in Cantonese.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Database Setup](#database-setup)
- [Running the Bot](#running-the-bot)
- [Admin Guide](#admin-guide)
- [Game Rounds Overview](#game-rounds-overview)
- [Shop & Items](#shop--items)
- [Nightly Schedule](#nightly-schedule)
- [Deployment Notes](#deployment-notes)

---

## Features

- **3-Round nightly game** — live battles, solo accuracy sprint, and 1v1 challenges
- **XP & rank progression** — 3 tiers (Beginner / Advanced / Elite), ranked within each tier
- **Coin economy** — earn coins, spend in shop; coins never buy XP
- **Power-up shop** — Shield, Extension, Double Down, Trap, Spy, and more
- **Badges & achievements** — First Blood, Perfect Round, Comeback Kid, and more
- **Streak tracking** — daily streaks with bonus rewards
- **Leaderboards** — tonight / weekly / all-time, by class and grade
- **Cross-class duels** — Round 3 challenges can target students in other classes
- **Weekly class tournament** — class-vs-class XP competition with coin prizes
- **Admin tools** — approve students, toggle topics, broadcast, manage channels, view stats
- **Nightly scheduler** — APScheduler handles all timed events automatically

---

## Architecture

```
Telegram Cloud
     | HTTPS (long-poll)
Python Bot (Mac Studio / VPS)
  +-- python-telegram-bot v21 (async)
  +-- asyncpg (PostgreSQL async driver)
  +-- APScheduler via JobQueue (cron)
  +-- PostgreSQL 15 (localhost:5432)
```

**Channel structure:**
```
Grade Channel       -- all 120 students, grade-wide announcements
Class A Channel     -- 30 students (甲班)
Class B Channel     -- 30 students (乙班)
Class C Channel     -- 30 students (丙班)
Class D Channel     -- 30 students (丁班)
```

---

## Project Structure

```
mathbot/
+-- main.py                  # Bot entry point, handler registration
+-- config.py                # All constants, env vars, game balance settings
+-- database.py              # All async database functions (asyncpg)
+-- requirements.txt
+-- .env.example             # Template for environment variables
+-- sql/
|   +-- schema.sql           # Full PostgreSQL schema
+-- handlers/
|   +-- __init__.py
|   +-- registration.py      # /start, student sign-up flow
|   +-- admin.py             # Admin commands (/approve, /stats, /broadcast, etc.)
|   +-- round1.py            # Live group battle handler
|   +-- round2.py            # Solo accuracy sprint + R3 challenge dispatch
|   +-- round3.py            # 1v1 peer challenge handler
|   +-- challenge.py         # Challenge inbox / accept / decline
|   +-- daily.py             # Daily question handler
|   +-- leaderboard.py       # Leaderboard display
|   +-- shop.py              # Shop browse, purchase, item use
+-- game/
|   +-- __init__.py
|   +-- questions.py         # Question selection logic
|   +-- scoring.py           # XP/coin formulas, streak bonuses
|   +-- ranks.py             # Rank tier definitions and thresholds
|   +-- twists.py            # Random twist events
+-- utils/
    +-- __init__.py
    +-- messages.py          # All Cantonese message templates
    +-- scheduler.py         # APScheduler job definitions
    +-- nightly.py           # Nightly reset logic (badges, streaks, snapshots)
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or higher |
| PostgreSQL | 15 or higher |
| A Telegram Bot Token | From [@BotFather](https://t.me/BotFather) |
| A machine with outbound HTTPS | Mac, VPS, or any server |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Cfsthk/mathbot.git
cd mathbot
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

```bash
cp .env.example .env
```

Then edit `.env` — see [Configuration](#configuration) below.

---

## Configuration

All settings live in `.env`. Copy `.env.example` and fill in each value:

```dotenv
# ---------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mathbot
DB_USER=postgres
DB_PASS=your_postgres_password

# ---------------------------------------------------------------
# ADMIN
# Comma-separated Telegram user IDs allowed to use /admin_* commands
# ---------------------------------------------------------------
ADMIN_TELEGRAM_IDS=123456789,987654321

# ---------------------------------------------------------------
# TELEGRAM CHANNEL IDS (optional — can also be set via /admin_setchannel)
# Get channel IDs by forwarding a message to @userinfobot
# ---------------------------------------------------------------
CHANNEL_P5A=-1001234567890
CHANNEL_P5B=-1001234567891
CHANNEL_P5C=-1001234567892
CHANNEL_P5D=-1001234567893
CHANNEL_P6A=-1001234567894
CHANNEL_P6B=-1001234567895
CHANNEL_P6C=-1001234567896
CHANNEL_P6D=-1001234567897
CHANNEL_GRADE_P5=-1001234567898
CHANNEL_GRADE_P6=-1001234567899
```

**Getting your Telegram channel ID:**
1. Add your bot as an admin to the channel
2. Forward any message from the channel to [@userinfobot](https://t.me/userinfobot)
3. It will show the channel ID (negative number starting with -100)

---

## Database Setup

### 1. Create the database

```bash
psql -U postgres
```

```sql
CREATE DATABASE mathbot;
\q
```

### 2. Run the schema

```bash
psql -U postgres -d mathbot -f sql/schema.sql
```

This creates all tables: `classes`, `students`, `questions`, `topics`, `battle_groups`, `battle_participants`, `round2_sessions`, `challenge_queue`, `challenge_responses`, `shop_items`, `inventory`, `item_usage_log`, `badges`, `student_badges`, `leaderboard_snapshots`, `daily_logs`, `weekly_tournaments`, and more.

### 3. Seed initial data (classes and shop items)

The schema includes `INSERT` statements for the 8 default classes (P5A–P6D) and all shop items. If you need a clean re-seed:

```bash
psql -U postgres -d mathbot -c "TRUNCATE classes, shop_items RESTART IDENTITY CASCADE;"
psql -U postgres -d mathbot -f sql/schema.sql
```

### 4. Add questions

Questions are inserted directly into the `questions` table. Minimum required fields:

```sql
INSERT INTO questions (topic_id, difficulty, tier, question_text, option_a, option_b, option_c, option_d, correct_option)
VALUES (1, 3, 1, '12 x 8 = ?', '96', '88', '104', '86', 'A');
```

---

## Running the Bot

### Development (foreground)

```bash
source venv/bin/activate
python main.py
```

You should see:
```
INFO - MathBot starting...
INFO - Database pool created (5 connections)
INFO - Scheduler started
INFO - Bot polling...
```

Press `Ctrl+C` to stop.

### Production (background with nohup)

```bash
nohup python main.py > logs/mathbot.log 2>&1 &
echo $! > mathbot.pid
```

To stop:
```bash
kill $(cat mathbot.pid)
```

### Production (systemd — recommended for Linux VPS)

Create `/etc/systemd/system/mathbot.service`:

```ini
[Unit]
Description=MathBot Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/mathbot
ExecStart=/home/ubuntu/mathbot/venv/bin/python main.py
Restart=on-failure
RestartSec=5
EnvironmentFile=/home/ubuntu/mathbot/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mathbot
sudo systemctl start mathbot
sudo systemctl status mathbot

# View live logs
journalctl -u mathbot -f
```

---

## Admin Guide

All admin commands start with `/admin_` and are restricted to `ADMIN_TELEGRAM_IDS`.

| Command | Description |
|---|---|
| `/admin_pending` | List students awaiting approval |
| `/admin_approve <id>` | Approve a student registration |
| `/admin_stats` | Today's participation stats |
| `/admin_broadcast <msg>` | Send message to all class channels |
| `/admin_setchannel <class> <channel_id>` | Set channel ID for a class |
| `/admin_toggletopic <topic_id>` | Enable/disable a question topic |
| `/admin_createboss` | Trigger a boss battle event |
| `/admin_reset` | Manually trigger nightly reset (use with care) |

**First-run checklist:**
1. Start the bot
2. DM the bot with `/start` to register yourself as admin
3. Add the bot as admin to all 5 channels
4. Set channel IDs via `/admin_setchannel` or `.env`
5. Insert questions into the database
6. Approve student registrations via `/admin_pending`

---

## Game Rounds Overview

### Round 1 — Live Group Battle (8:00 pm)
- Students in the same class are grouped by tier (Beginner / Advanced / Elite)
- Each group receives 1 multiple-choice question via inline keyboard
- Answer speed determines finish position (1st–5th)
- XP and coins awarded based on correctness + speed
- Power-ups (Shield, Double Down, Trap) activate here

### Round 2 — Solo Accuracy Sprint (~8:20 pm)
- Each student receives 5 questions at their difficulty level
- Students choose a difficulty adjustment (-2 to +2) before starting
- XP scales with accuracy and difficulty
- Completing R2 unlocks the option to send a Round 3 challenge

### Round 3 — Peer Challenge (~8:40 pm)
- Students pick a classmate (or cross-class rival) to challenge
- Challenger sets the question; receiver has until midnight to answer
- XP flows both ways depending on outcome
- Items like 指定券 (Forced Challenge) and 陷阱券 (Trap) modify outcomes

---

## Shop & Items

| Item | Effect |
|---|---|
| 護盾 Shield | Blocks incoming traps for 1 session |
| 延長券 Extension | Extends Round 2 deadline by 15 minutes |
| 雙倍賭注 Double Down | Doubles XP stake on your next R3 challenge |
| 陷阱券 Trap | Sends a harder question to your R3 target |
| 指定券 Forced Challenge | Forces a specific student to receive your R3 |
| 間諜券 Spy | Reveals the answer used by another student (once per session) |

Items are purchased with coins and stored in the student's inventory. The shop is accessible anytime via `/shop`.

---

## Nightly Schedule

| Time (HKT) | Event |
|---|---|
| 19:45 | Round 1 reminder sent to class channels |
| 20:00 | Round 1 opens (battle groups created) |
| 20:15 | Round 1 closes (unanswered groups auto-closed) |
| 20:20 | Round 2 begins |
| 22:00 | Round 2 hard close |
| 00:00 | Expire pending challenges, reset nightly flags, update streaks, award badges, snapshot leaderboard |
| Monday 00:00 | Resolve weekly class tournament, distribute prizes |

---

## Deployment Notes

- The bot uses **long polling** (no webhook needed) — works behind NAT with no port forwarding
- Keep PostgreSQL on localhost for lowest latency
- The `.env` file contains secrets — never commit it to version control (it is in `.gitignore`)
- Logs are written to stdout/stderr; redirect to a file or use `journalctl` in production
- All scheduler jobs use Asia/Hong_Kong timezone (UTC+8)
- The bot is designed for ~120 concurrent students; asyncpg pool size of 10 is sufficient

---

## License

MIT
