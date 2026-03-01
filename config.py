"""
config.py — MathBot MVP v2.0
All constants, environment variables, and game balance settings.
"""
import os
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# TELEGRAM
# =============================================================================

BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# =============================================================================
# DATABASE
# =============================================================================

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'mathbot')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', '')

# =============================================================================
# ADMIN
# =============================================================================

_admin_str = os.getenv('ADMIN_TELEGRAM_IDS', '')
ADMIN_TELEGRAM_IDS: List[int] = [
    int(x.strip()) for x in _admin_str.split(',')
    if x.strip().isdigit()
] if _admin_str else []

# =============================================================================
# TIMEZONE
# =============================================================================

TIMEZONE = "Asia/Hong_Kong"

# =============================================================================
# GRADE & CLASS STRUCTURE
# =============================================================================

# Supported grades
VALID_GRADES = ['P5', 'P6']

# Class codes per grade — 4 classes each
VALID_CLASS_CODES = [
    'P5A', 'P5B', 'P5C', 'P5D',
    'P6A', 'P6B', 'P6C', 'P6D',
]

# Display names for classes (maps class_code -> Cantonese name)
CLASS_DISPLAY_NAMES: Dict[str, str] = {
    'P5A': '甲班', 'P5B': '乙班', 'P5C': '丙班', 'P5D': '丁班',
    'P6A': '甲班', 'P6B': '乙班', 'P6C': '丙班', 'P6D': '丁班',
}

# Telegram channel IDs — set via /admin_setchannel command, stored in DB.
# These env vars are fallback defaults for first-run setup.
# Format: CHANNEL_P6A, CHANNEL_P6B, CHANNEL_P6C, CHANNEL_P6D, CHANNEL_GRADE_P6
CLASS_CHANNELS: Dict[str, int] = {
    code: int(os.getenv(f'CHANNEL_{code}', '0'))
    for code in VALID_CLASS_CODES
}
GRADE_CHANNELS: Dict[str, int] = {
    grade: int(os.getenv(f'CHANNEL_GRADE_{grade}', '0'))
    for grade in VALID_GRADES
}

# =============================================================================
# NIGHTLY SCHEDULE (HKT = UTC+8)
# =============================================================================

# Round 1: Live battle opens
R1_HOUR   = 20   # 8:00pm HKT
R1_MINUTE = 0

# Round 1: Reminder sent to group channel
R1_REMINDER_HOUR   = 19
R1_REMINDER_MINUTE = 45

# Round 1: Auto-close groups after this many minutes
R1_DURATION_MINUTES = 15

# Round 2: Hard close (protect sleep)
R2_CLOSE_HOUR   = 22   # 10:00pm HKT
R2_CLOSE_MINUTE = 0

# Midnight: expire challenges, reset flags
MIDNIGHT_HOUR   = 0
MIDNIGHT_MINUTE = 0

# Weekly tournament reset: every Monday 00:00 HKT
WEEKLY_RESET_DAY    = 0   # Monday (0=Mon, 6=Sun)
WEEKLY_RESET_HOUR   = 0
WEEKLY_RESET_MINUTE = 0

# Weekly tournament resolve: every Sunday 23:55 HKT
WEEKLY_RESOLVE_DAY    = 6
WEEKLY_RESOLVE_HOUR   = 23
WEEKLY_RESOLVE_MINUTE = 55

# =============================================================================
# ROUND 1 — LIVE BATTLE
# =============================================================================

R1_GROUP_SIZE       = 3     # target group size
R1_MAX_GROUP_SIZE   = 5     # lowest tier can have up to 5
R1_NO_RETRY         = True  # one shot, no retry on wrong answer

# XP rewards by finish position
R1_XP_REWARDS: Dict[int, int] = {
    1: 80,   # 1st correct
    2: 40,   # 2nd correct
    3: 20,   # 3rd correct
    4: 10,   # 4th+ correct (lowest tier groups of 4-5)
    0: 10,   # wrong answer — small participation XP
}

# Coin rewards by finish position
R1_COIN_REWARDS: Dict[int, int] = {
    1: 15,
    2: 5,
    3: 0,
    4: 0,
    0: 0,
}

# =============================================================================
# ROUND 2 — SOLO ACCURACY
# =============================================================================

R2_QUESTION_COUNT = 5

# Accuracy thresholds -> allowed difficulty adjustment range [min, max]
R2_ACCURACY_ADJUSTMENTS: List[Dict] = [
    {'min_accuracy': 100, 'adj_min': -2, 'adj_max': 2},
    {'min_accuracy': 80,  'adj_min': -1, 'adj_max': 2},
    {'min_accuracy': 60,  'adj_min':  0, 'adj_max': 1},
    {'min_accuracy': 40,  'adj_min':  0, 'adj_max': 0},
    {'min_accuracy': 0,   'adj_min': -1, 'adj_max': 0},
]

# XP for completing Round 2
R2_XP_BASE         = 50
R2_XP_PERFECT_BONUS = 20   # extra for 100% accuracy

# =============================================================================
# ROUND 3 — PEER CHALLENGES
# =============================================================================

MAX_CHALLENGES_SENT_R2  = 1    # per night from own R2
MAX_CHALLENGES_SENT_R3  = 1    # per night forwarded from received R3
MAX_CHALLENGES_RECEIVED = 3    # per student per night

# Difficulty cap: receiver never gets question above their tier base + this value
R3_DIFFICULTY_CAP_ABOVE_TIER = 1

# Cross-class allowed: same tier only
R3_CROSS_CLASS_ENABLED    = True
R3_CROSS_CLASS_SAME_TIER  = True

# Class Pride bonus for correct cross-class answer
R3_CLASS_PRIDE_COINS = 5

# XP rewards for receiver
R3_XP_BASE = 50

# Tier gap multipliers for receiver XP (tier_gap = sender_tier - receiver_tier)
R3_RECEIVER_XP_MULTIPLIERS: Dict[int, float] = {
    -2: 0.5,   # sender 2 tiers below (easy question)
    -1: 0.75,  # sender 1 tier below
     0: 1.0,   # same tier
     1: 1.5,   # sender 1 tier above
     2: 2.0,   # sender 2 tiers above
     3: 3.0,   # sender 3+ tiers above (capped)
}

# Consolation XP for wrong answer (only when sender tier > receiver tier)
R3_CONSOLATION_XP: Dict[int, int] = {
    0:  0,    # same tier, wrong = nothing
    1: 15,    # 1 tier above, wrong = consolation
    2: 25,    # 2 tiers above, wrong = more consolation
    3: 35,    # 3+ tiers above, wrong = generous consolation
}

# Sender XP when their challenge gets answered
R3_SENDER_XP_RECEIVER_CORRECT   = 15   # receiver got it right (fair challenge)
R3_SENDER_XP_RECEIVER_WRONG     = 25   # receiver got it wrong (hard challenge)

# Trap item: XP deducted from receiver on wrong answer
R3_TRAP_XP_PENALTY = 10

# Double-down: sender XP multiplier when receiver is wrong
R3_DOUBLE_DOWN_MULTIPLIER = 2.0

# =============================================================================
# RANK TIER SYSTEM (12 ranks, 3 tiers)
# =============================================================================

# tier 1 = Beginner (ranks 1-4)
# tier 2 = Advanced (ranks 5-8)
# tier 3 = Elite    (ranks 9-12)

RANK_TIERS: List[Dict[str, Any]] = [
    {'rank': 1,  'tier': 1, 'title_zh': '數字新丁',   'title_en': 'Number Novice',       'xp_required': 0},
    {'rank': 2,  'tier': 1, 'title_zh': '算術學徒',   'title_en': 'Arithmetic Apprentice','xp_required': 200},
    {'rank': 3,  'tier': 1, 'title_zh': '分數戰士',   'title_en': 'Fraction Fighter',     'xp_required': 450},
    {'rank': 4,  'tier': 1, 'title_zh': '小數俠客',   'title_en': 'Decimal Duelist',      'xp_required': 750},
    {'rank': 5,  'tier': 2, 'title_zh': '百分達人',   'title_en': 'Percentage Pro',       'xp_required': 1100},
    {'rank': 6,  'tier': 2, 'title_zh': '幾何守衛',   'title_en': 'Geometry Guardian',    'xp_required': 1500},
    {'rank': 7,  'tier': 2, 'title_zh': '代數騎士',   'title_en': 'Algebra Knight',       'xp_required': 2000},
    {'rank': 8,  'tier': 2, 'title_zh': '比率劍客',   'title_en': 'Ratio Swordsman',      'xp_required': 2600},
    {'rank': 9,  'tier': 3, 'title_zh': '方程式武士', 'title_en': 'Equation Samurai',     'xp_required': 3300},
    {'rank': 10, 'tier': 3, 'title_zh': '數據將軍',   'title_en': 'Data General',         'xp_required': 4100},
    {'rank': 11, 'tier': 3, 'title_zh': '邏輯宗師',   'title_en': 'Logic Grandmaster',    'xp_required': 5000},
    {'rank': 12, 'tier': 3, 'title_zh': '數學帝王',   'title_en': 'Math Emperor',         'xp_required': 6000},
]

TIER_ICONS: Dict[int, str] = {
    1: '📚',   # Beginner
    2: '🔥',   # Advanced
    3: '👑',   # Elite
}

TIER_NAMES: Dict[int, str] = {
    1: '初階',
    2: '進階',
    3: '精英',
}

# Question difficulty range per tier (used to pick R1/R2 questions)
TIER_DIFFICULTY_RANGE: Dict[int, tuple] = {
    1: (1, 3),    # Beginner:  difficulty 1-3
    2: (4, 6),    # Advanced:  difficulty 4-6
    3: (7, 10),   # Elite:     difficulty 7-10
}

# Default base difficulty per tier for R2
TIER_BASE_DIFFICULTY: Dict[int, int] = {
    1: 2,
    2: 5,
    3: 8,
}

# =============================================================================
# STREAK BONUSES
# =============================================================================

STREAK_BONUSES: Dict[int, Dict[str, Any]] = {
    3:  {'xp_bonus_pct': 10,  'coins_bonus': 0,  'badge': None},
    7:  {'xp_bonus_pct': 20,  'coins_bonus': 10, 'badge': 'seven_streak'},
    14: {'xp_bonus_pct': 30,  'coins_bonus': 15, 'badge': 'fourteen_streak'},
    30: {'xp_bonus_pct': 50,  'coins_bonus': 25, 'badge': 'thirty_streak'},
}

# =============================================================================
# WEEKLY TOURNAMENT PRIZES (coins)
# =============================================================================

TOURNAMENT_PRIZES_CLASS: List[int] = [50, 30, 20]   # 1st, 2nd, 3rd (class tourney)
TOURNAMENT_PRIZES_GRADE: List[int] = [80, 50, 30]   # 1st, 2nd, 3rd (grade tourney)

# =============================================================================
# CONVERSATION STATES
# =============================================================================

STATE_AWAITING_CLASS    = 1
STATE_AWAITING_NAME     = 2
STATE_AWAITING_GRADE    = 3

# =============================================================================
# CALLBACK DATA PREFIXES
# =============================================================================

CB_R1_ANSWER        = "r1_ans_"        # r1_ans_{group_id}_{option_index}
CB_R2_ANSWER        = "r2_ans_"        # r2_ans_{session_id}_{q_order}_{option_index}
CB_R2_ADJ           = "r2_adj_"        # r2_adj_{session_id}_{adjustment}
CB_R2_TARGET        = "r2_tgt_"        # r2_tgt_{session_id}_{receiver_id}
CB_R3_ACCEPT        = "r3_accept_"     # r3_accept_{challenge_id}
CB_R3_DECLINE       = "r3_decline_"    # r3_decline_{challenge_id}
CB_R3_ANSWER        = "r3_ans_"        # r3_ans_{challenge_id}_{q_index}_{option_index}
CB_R3_FORWARD       = "r3_fwd_"        # r3_fwd_{challenge_id}_{receiver_id}
CB_SHOP_CAT         = "shop_cat_"      # shop_cat_{category}
CB_SHOP_BUY         = "shop_buy_"      # shop_buy_{effect_key}
CB_SHOP_CONFIRM     = "shop_confirm_"  # shop_confirm_{effect_key}
CB_INV_USE          = "inv_use_"       # inv_use_{effect_key}
CB_SPY_TARGET       = "spy_tgt_"       # spy_tgt_{target_student_id}
CB_ADMIN_APPROVE    = "adm_approve_"   # adm_approve_{student_id}
CB_TOPIC_TOGGLE     = "topic_toggle_"  # topic_toggle_{topic_id}
CB_LB_VIEW          = "lb_"            # lb_tonight | lb_week | lb_grade | lb_class | lb_all

# =============================================================================
# SHOP ITEMS
# Runtime reference for handlers — prices/names must stay in sync with DB seed.
# =============================================================================

SHOP_ITEMS: Dict[str, Dict[str, Any]] = {
    "shield": {
        "name_zh":       "護盾",
        "description_zh": "保護你一次不被挑戰扣XP",
        "icon":          "🛡",
        "price":         50,
        "category":      "ability",
        "max_hold":      3,
        # When used: sets students.shield_active = TRUE (reset nightly)
        "flag_col":      "shield_active",
        "use_mode":      "auto",        # activates immediately, triggers on next incoming challenge
    },
    "extension": {
        "name_zh":       "延時券",
        "description_zh": "將今晚挑戰期限延至明早8am",
        "icon":          "⏰",
        "price":         30,
        "category":      "ability",
        "max_hold":      2,
        "flag_col":      "extension_active",
        "use_mode":      "auto",
    },
    "spy": {
        "name_zh":       "窺探券",
        "description_zh": "查看目標同學的Round 2準確率",
        "icon":          "🔍",
        "price":         40,
        "category":      "ability",
        "max_hold":      2,
        "flag_col":      "spy_used_today",
        "use_mode":      "pick_target",  # prompts target picker before activating
    },
    "reset": {
        "name_zh":       "重置券",
        "description_zh": "重置今晚Round 2題目（只限一次）",
        "icon":          "🔄",
        "price":         80,
        "category":      "ability",
        "max_hold":      1,
        "flag_col":      None,           # no persistent flag — consumed on use
        "use_mode":      "consume",
    },
    "double_down": {
        "name_zh":       "雙倍賭注",
        "description_zh": "你的挑戰若對方答錯，你得雙倍XP",
        "icon":          "💥",
        "price":         60,
        "category":      "challenge",
        "max_hold":      2,
        "flag_col":      "double_down_active",
        "use_mode":      "auto",
    },
    "target": {
        "name_zh":       "指定券",
        "description_zh": "強制某同學必須接受你的挑戰",
        "icon":          "🎯",
        "price":         20,
        "category":      "challenge",
        "max_hold":      3,
        "flag_col":      None,
        "use_mode":      "consume",
    },
    "trap": {
        "name_zh":       "陷阱券",
        "description_zh": "對方答錯你的挑戰時，對方額外失去少量XP",
        "icon":          "🪤",
        "price":         70,
        "category":      "challenge",
        "max_hold":      2,
        "flag_col":      "trap_active",
        "use_mode":      "auto",
    },
    "title_frame": {
        "name_zh":       "頭銜框",
        "description_zh": "在排行榜名字旁顯示特別頭銜",
        "icon":          "🖼",
        "price":         100,
        "category":      "cosmetic",
        "max_hold":      1,
        "flag_col":      None,
        "use_mode":      "cosmetic",
    },
    "star_mark": {
        "name_zh":       "星級標記",
        "description_zh": "排行榜顯示特別星級標記",
        "icon":          "⭐",
        "price":         80,
        "category":      "cosmetic",
        "max_hold":      1,
        "flag_col":      None,
        "use_mode":      "cosmetic",
    },
}
