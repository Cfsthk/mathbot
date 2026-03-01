# MathBot 數學機械人

一個基於 Telegram 的競技數學遊戲，專為香港小學生（小五/小六）設計。每晚舉行三輪遊戲，結合即時群組對戰、個人準確度挑戰及同學互相對決——全程在 Telegram 內透過內嵌鍵盤操作。進度以 XP、段位、金幣、連勝及徽章追蹤，並設有金幣商店提供各種策略道具。

> 所有遊戲內訊息均以粵語顯示。

---

## 目錄

- [功能特色](#功能特色)
- [系統架構](#系統架構)
- [項目結構](#項目結構)
- [系統需求](#系統需求)
- [安裝步驟](#安裝步驟)
- [設定說明](#設定說明)
- [資料庫設定](#資料庫設定)
- [啟動機械人](#啟動機械人)
- [管理員指南](#管理員指南)
- [遊戲回合概覽](#遊戲回合概覽)
- [商店與道具](#商店與道具)
- [每晚時間表](#每晚時間表)
- [部署注意事項](#部署注意事項)

---

## 功能特色

- **每晚三輪遊戲** — 即時群組對戰、個人準確度衝刺及一對一挑戰
- **XP 與段位晉升** — 三個等級（初階 / 進階 / 精英），各級內部排名
- **金幣經濟** — 賺取金幣，在商店消費；金幣不能購買 XP，競技公平性不受影響
- **道具商店** — 護盾、延長券、雙倍賭注、陷阱券、間諜券等
- **徽章與成就** — 首殺、完美回合、逆轉勝等
- **連勝追蹤** — 每日連勝並附加獎勵
- **排行榜** — 今晚 / 本週 / 全期，按班級及年級分類
- **跨班挑戰** — 第三回合可向其他班級的同學發起挑戰
- **每週班際錦標賽** — 班對班 XP 競賽，設有金幣獎勵
- **管理員工具** — 審批學生、切換題目類別、廣播、管理頻道、查看統計
- **每晚自動排程** — APScheduler 自動處理所有定時事件

---

## 系統架構

```
Telegram 雲端
     | HTTPS（長輪詢）
Python 機械人（Mac Studio / VPS）
  +-- python-telegram-bot v21（非同步）
  +-- asyncpg（PostgreSQL 非同步驅動）
  +-- APScheduler（透過 JobQueue 定時）
  +-- PostgreSQL 15（localhost:5432）
```

**頻道結構：**
```
年級頻道（全級頻道）    — 全部 120 名學生訂閱，年級公告
甲班頻道               — 30 名學生
乙班頻道               — 30 名學生
丙班頻道               — 30 名學生
丁班頻道               — 30 名學生
```

---

## 項目結構

```
mathbot/
+-- main.py                  # 機械人入口，處理器註冊
+-- config.py                # 所有常數、環境變數、遊戲平衡設定
+-- database.py              # 所有非同步資料庫函數（asyncpg）
+-- requirements.txt
+-- .env.example             # 環境變數範本
+-- sql/
|   +-- schema.sql           # 完整 PostgreSQL 資料庫結構
+-- handlers/
|   +-- __init__.py
|   +-- registration.py      # /start，學生註冊流程
|   +-- admin.py             # 管理員指令（/approve、/stats、/broadcast 等）
|   +-- round1.py            # 即時群組對戰處理器
|   +-- round2.py            # 個人準確度衝刺 + 第三回合挑戰派發
|   +-- round3.py            # 一對一同學挑戰處理器
|   +-- challenge.py         # 挑戰收件箱 / 接受 / 拒絕
|   +-- daily.py             # 每日題目處理器
|   +-- leaderboard.py       # 排行榜顯示
|   +-- shop.py              # 商店瀏覽、購買、使用道具
+-- game/
|   +-- __init__.py
|   +-- questions.py         # 題目選取邏輯
|   +-- scoring.py           # XP / 金幣公式、連勝加成
|   +-- ranks.py             # 段位等級定義與門檻
|   +-- twists.py            # 隨機變化事件
+-- utils/
    +-- __init__.py
    +-- messages.py          # 所有粵語訊息範本
    +-- scheduler.py         # APScheduler 工作定義
    +-- nightly.py           # 每晚重置邏輯（徽章、連勝、快照）
```

---

## 系統需求

| 需求 | 版本 |
|---|---|
| Python | 3.11 或以上 |
| PostgreSQL | 15 或以上 |
| Telegram 機械人 Token | 透過 [@BotFather](https://t.me/BotFather) 取得 |
| 可對外 HTTPS 的機器 | Mac、VPS 或任何伺服器 |

---

## 安裝步驟

### 第一步：複製儲存庫

```bash
git clone https://github.com/Cfsthk/mathbot.git
cd mathbot
```

### 第二步：建立並啟動虛擬環境

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 第三步：安裝依賴套件

```bash
pip install -r requirements.txt
```

### 第四步：建立 `.env` 設定檔

```bash
cp .env.example .env
```

然後編輯 `.env`，詳見下方 [設定說明](#設定說明)。

---

## 設定說明

所有設定均存放於 `.env`。複製 `.env.example` 後填入各項數值：

```dotenv
# ---------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ---------------------------------------------------------------
# 資料庫
# ---------------------------------------------------------------
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mathbot
DB_USER=postgres
DB_PASS=你的postgres密碼

# ---------------------------------------------------------------
# 管理員
# 以逗號分隔的 Telegram 用戶 ID，可使用 /admin_* 指令
# ---------------------------------------------------------------
ADMIN_TELEGRAM_IDS=123456789,987654321

# ---------------------------------------------------------------
# TELEGRAM 頻道 ID（選填 — 也可透過 /admin_setchannel 設定）
# 透過將訊息轉發至 @userinfobot 取得頻道 ID
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

**取得 Telegram 頻道 ID 的方法：**
1. 將機械人設為該頻道的管理員
2. 將頻道內任意訊息轉發至 [@userinfobot](https://t.me/userinfobot)
3. 它會顯示頻道 ID（以 -100 開頭的負數）

---

## 資料庫設定

### 第一步：建立資料庫

```bash
psql -U postgres
```

```sql
CREATE DATABASE mathbot;
\q
```

### 第二步：執行資料庫結構腳本

```bash
psql -U postgres -d mathbot -f sql/schema.sql
```

此步驟會建立所有資料表：`classes`、`students`、`questions`、`topics`、`battle_groups`、`battle_participants`、`round2_sessions`、`challenge_queue`、`challenge_responses`、`shop_items`、`inventory`、`item_usage_log`、`badges`、`student_badges`、`leaderboard_snapshots`、`daily_logs`、`weekly_tournaments` 等。

### 第三步：載入初始資料（班級與商店道具）

資料庫結構腳本已包含 8 個預設班級（P5A–P6D）及所有商店道具的 `INSERT` 語句。如需重新載入：

```bash
psql -U postgres -d mathbot -c "TRUNCATE classes, shop_items RESTART IDENTITY CASCADE;"
psql -U postgres -d mathbot -f sql/schema.sql
```

### 第四步：新增題目

題目直接插入 `questions` 資料表，最少必填欄位如下：

```sql
INSERT INTO questions (topic_id, difficulty, tier, question_text, option_a, option_b, option_c, option_d, correct_option)
VALUES (1, 3, 1, '12 x 8 = ?', '96', '88', '104', '86', 'A');
```

---

## 啟動機械人

### 開發模式（前台執行）

```bash
source venv/bin/activate
python main.py
```

正常啟動後應顯示：
```
INFO - MathBot starting...
INFO - Database pool created (5 connections)
INFO - Scheduler started
INFO - Bot polling...
```

按 `Ctrl+C` 停止。

### 生產模式（使用 nohup 後台執行）

```bash
nohup python main.py > logs/mathbot.log 2>&1 &
echo $! > mathbot.pid
```

停止機械人：
```bash
kill $(cat mathbot.pid)
```

### 生產模式（systemd — 適用於 Linux VPS，推薦）

建立 `/etc/systemd/system/mathbot.service`：

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

執行以下指令：
```bash
sudo systemctl daemon-reload
sudo systemctl enable mathbot
sudo systemctl start mathbot
sudo systemctl status mathbot

# 查看即時日誌
journalctl -u mathbot -f
```

---

## 管理員指南

所有管理員指令以 `/admin_` 開頭，僅限 `ADMIN_TELEGRAM_IDS` 中的用戶使用。

| 指令 | 說明 |
|---|---|
| `/admin_pending` | 列出待審批的學生 |
| `/admin_approve <id>` | 審批學生註冊 |
| `/admin_stats` | 今日參與統計 |
| `/admin_broadcast <訊息>` | 向所有班級頻道發送訊息 |
| `/admin_setchannel <班級> <頻道ID>` | 設定班級的頻道 ID |
| `/admin_toggletopic <topic_id>` | 啟用 / 停用某個題目類別 |
| `/admin_createboss` | 觸發首領對戰活動 |
| `/admin_reset` | 手動觸發每晚重置（謹慎使用） |

**首次使用清單：**
1. 啟動機械人
2. 私訊機械人 `/start`，以管理員身份完成註冊
3. 將機械人設為全部 5 個頻道的管理員
4. 透過 `/admin_setchannel` 或 `.env` 設定頻道 ID
5. 在資料庫插入題目
6. 透過 `/admin_pending` 審批學生註冊申請

---

## 遊戲回合概覽

### 第一回合 — 即時群組對戰（晚上 8:00）
- 同班同學按等級（初階 / 進階 / 精英）分組
- 每組透過內嵌鍵盤收到一道選擇題
- 答題速度決定完成名次（第 1–5 名）
- XP 和金幣根據正確率及速度發放
- 道具（護盾、雙倍賭注、陷阱券）在此回合生效

### 第二回合 — 個人準確度衝刺（約晚上 8:20）
- 每位學生收到 5 道符合自身難度的題目
- 學生可在開始前選擇難度調整（-2 至 +2）
- XP 按準確率及難度計算
- 完成第二回合後可解鎖發送第三回合挑戰的選項

### 第三回合 — 同學互相挑戰（約晚上 8:40）
- 學生選擇班內同學（或跨班對手）發起挑戰
- 挑戰方設定題目；接收方需在午夜前作答
- 雙方均可根據結果獲得 XP
- 指定券、陷阱券等道具可改變挑戰結果

---

## 商店與道具

| 道具 | 效果 |
|---|---|
| 護盾 | 阻擋一次本場的陷阱攻擊 |
| 延長券 | 將第二回合截止時間延長 15 分鐘 |
| 雙倍賭注 | 下一次第三回合挑戰的 XP 賭注加倍 |
| 陷阱券 | 向第三回合目標發送更難的題目 |
| 指定券 | 強制指定某位學生接受你的第三回合挑戰 |
| 間諜券 | 查看另一位學生本場所用的答案（每場限用一次） |

道具以金幣購買，存放於學生的背包。商店可隨時透過 `/shop` 存取。

---

## 每晚時間表

| 時間（香港時間） | 事件 |
|---|---|
| 19:45 | 向班級頻道發送第一回合提醒 |
| 20:00 | 第一回合開始（建立對戰組別） |
| 20:15 | 第一回合結束（未作答的組別自動關閉） |
| 20:20 | 第二回合開始 |
| 22:00 | 第二回合強制結束 |
| 00:00 | 過期待處理挑戰、重置每晚旗標、更新連勝、頒發徽章、排行榜快照 |
| 每週一 00:00 | 結算每週班際錦標賽、發放獎勵 |

---

## 部署注意事項

- 機械人使用**長輪詢**（無需 Webhook），可在 NAT 後方運行，無需轉發端口
- 將 PostgreSQL 保持在本機以獲得最低延遲
- `.env` 檔案包含敏感資訊——切勿提交至版本控制（已列入 `.gitignore`）
- 日誌輸出至 stdout/stderr；在生產環境中重定向至檔案或使用 `journalctl`
- 所有排程工作使用香港時區（UTC+8）
- 機械人設計支援約 120 名同時在線學生；asyncpg 連線池大小 10 已足夠

---

## 授權

MIT
