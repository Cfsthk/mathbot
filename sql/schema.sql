-- =============================================================================
-- MathBot MVP Database Schema v2.0
-- Hong Kong Primary School Math Game — Grade-wide, 4 classes, 120 students
-- =============================================================================

-- =============================================================================
-- CORE STRUCTURE
-- =============================================================================

-- Classes (4 per grade: A, B, C, D)
CREATE TABLE IF NOT EXISTS classes (
    id              SERIAL PRIMARY KEY,
    class_code      TEXT UNIQUE NOT NULL,       -- e.g. P6A, P6B
    grade           TEXT NOT NULL,              -- P5, P6
    display_name    TEXT NOT NULL,              -- e.g. 甲班, 乙班, 丙班, 丁班
    channel_id      BIGINT,                     -- Telegram channel ID for announcements
    student_count   INTEGER DEFAULT 0,
    CONSTRAINT valid_grade CHECK (grade IN ('P5', 'P6'))
);

CREATE INDEX idx_classes_grade ON classes(grade);

-- Grade channels (one per grade for cross-class announcements)
CREATE TABLE IF NOT EXISTS grade_channels (
    id              SERIAL PRIMARY KEY,
    grade           TEXT UNIQUE NOT NULL,
    channel_id      BIGINT NOT NULL,
    CONSTRAINT valid_grade CHECK (grade IN ('P5', 'P6'))
);

-- Students
CREATE TABLE IF NOT EXISTS students (
    id                      SERIAL PRIMARY KEY,
    telegram_id             BIGINT UNIQUE NOT NULL,
    username                TEXT,
    display_name            TEXT NOT NULL,
    class_id                INTEGER REFERENCES classes(id),
    grade                   TEXT NOT NULL,
    xp                      INTEGER DEFAULT 0,
    coins                   INTEGER DEFAULT 0,
    rank_num                INTEGER DEFAULT 1,          -- 1-12
    tier                    INTEGER DEFAULT 1,          -- 1=Beginner 2=Advanced 3=Elite
    streak                  INTEGER DEFAULT 0,
    last_active_date        DATE,
    is_active               BOOLEAN DEFAULT FALSE,      -- admin must approve
    joined_at               TIMESTAMP DEFAULT NOW(),
    -- Item flags (reset nightly by scheduler)
    shield_active           BOOLEAN DEFAULT FALSE,
    extension_active        BOOLEAN DEFAULT FALSE,
    double_down_active      BOOLEAN DEFAULT FALSE,
    trap_active             BOOLEAN DEFAULT FALSE,
    spy_used_today          BOOLEAN DEFAULT FALSE,
    -- Weekly tournament XP (resets each Monday)
    weekly_xp               INTEGER DEFAULT 0,
    -- Tonight's round tracking (reset each night by scheduler)
    r2_sends_tonight        INTEGER DEFAULT 0,          -- max 1 from own R2
    r3_sends_tonight        INTEGER DEFAULT 0,          -- max 1 forwarded from R3
    r3_received_tonight     INTEGER DEFAULT 0,          -- max 3
    CONSTRAINT valid_rank CHECK (rank_num BETWEEN 1 AND 12),
    CONSTRAINT valid_tier CHECK (tier BETWEEN 1 AND 3)
);

CREATE INDEX idx_students_telegram_id ON students(telegram_id);
CREATE INDEX idx_students_class_id ON students(class_id);
CREATE INDEX idx_students_grade ON students(grade);
CREATE INDEX idx_students_tier ON students(tier);
CREATE INDEX idx_students_xp ON students(xp DESC);
CREATE INDEX idx_students_is_active ON students(is_active);

-- =============================================================================
-- QUESTIONS & TOPICS
-- =============================================================================

CREATE TABLE IF NOT EXISTS topics (
    id          SERIAL PRIMARY KEY,
    name_en     TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    grade       TEXT NOT NULL,              -- P5, P6, BOTH
    is_active   BOOLEAN DEFAULT FALSE,
    sort_order  INTEGER DEFAULT 0,
    CONSTRAINT valid_topic_grade CHECK (grade IN ('P5', 'P6', 'BOTH'))
);

CREATE INDEX idx_topics_grade ON topics(grade);
CREATE INDEX idx_topics_is_active ON topics(is_active);

CREATE TABLE IF NOT EXISTS questions (
    id                      SERIAL PRIMARY KEY,
    topic_id                INTEGER REFERENCES topics(id),
    difficulty              INTEGER CHECK (difficulty BETWEEN 1 AND 10),
    question_template       TEXT NOT NULL,      -- Cantonese with {A},{B} placeholders
    answer_formula          TEXT NOT NULL,      -- Python-evaluable e.g. "{A}*{B}"
    option_formulas         TEXT[] NOT NULL,    -- 4 MCQ option formulas
    correct_option_index    INTEGER NOT NULL,
    param_ranges            JSONB NOT NULL,     -- {"A": [1,10], "B": [2,5]}
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_correct_index CHECK (correct_option_index BETWEEN 0 AND 3)
);

CREATE INDEX idx_questions_topic_id ON questions(topic_id);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_is_active ON questions(is_active);

-- =============================================================================
-- ROUND 1 — LIVE BATTLE
-- =============================================================================

-- One battle session per night
CREATE TABLE IF NOT EXISTS battle_sessions (
    id              SERIAL PRIMARY KEY,
    session_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    grade           TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',     -- pending, active, closed
    opened_at       TIMESTAMP,
    closed_at       TIMESTAMP,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'active', 'closed'))
);

CREATE INDEX idx_battle_sessions_date ON battle_sessions(session_date);
CREATE UNIQUE INDEX idx_battle_sessions_date_grade ON battle_sessions(session_date, grade);

-- Groups of 3 (or up to 5 for lowest tier) formed at 8pm
CREATE TABLE IF NOT EXISTS battle_groups (
    id                  SERIAL PRIMARY KEY,
    session_id          INTEGER REFERENCES battle_sessions(id),
    tier                INTEGER NOT NULL,               -- 1, 2, 3
    question_id         INTEGER REFERENCES questions(id),
    params              JSONB,
    options             JSONB,
    correct_index       INTEGER,
    status              TEXT DEFAULT 'waiting',         -- waiting, active, closed
    opened_at           TIMESTAMP,
    closed_at           TIMESTAMP,                      -- 15 min after opened
    winner_id           INTEGER REFERENCES students(id),
    CONSTRAINT valid_group_status CHECK (status IN ('waiting', 'active', 'closed'))
);

CREATE INDEX idx_battle_groups_session_id ON battle_groups(session_id);
CREATE INDEX idx_battle_groups_tier ON battle_groups(tier);

-- Group membership
CREATE TABLE IF NOT EXISTS battle_group_members (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES battle_groups(id),
    student_id      INTEGER REFERENCES students(id),
    answer_index    INTEGER,                            -- which option they chose
    is_correct      BOOLEAN,
    answered_at     TIMESTAMP,
    finish_position INTEGER,                            -- 1st, 2nd, 3rd correct
    xp_earned       INTEGER DEFAULT 0,
    coins_earned    INTEGER DEFAULT 0,
    UNIQUE(group_id, student_id)
);

CREATE INDEX idx_battle_group_members_group_id ON battle_group_members(group_id);
CREATE INDEX idx_battle_group_members_student_id ON battle_group_members(student_id);

-- =============================================================================
-- ROUND 2 — SOLO ACCURACY CHALLENGE
-- =============================================================================

-- One session per student per night
CREATE TABLE IF NOT EXISTS round2_sessions (
    id              SERIAL PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id),
    session_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    status          TEXT DEFAULT 'pending',     -- pending, active, completed, expired
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    total_questions INTEGER DEFAULT 5,
    correct_count   INTEGER DEFAULT 0,
    accuracy        NUMERIC(5,2),               -- 0.00 to 100.00
    difficulty_base INTEGER,                    -- student's tier base difficulty
    difficulty_adjustment INTEGER DEFAULT 0,    -- chosen adjustment -2 to +2
    final_difficulty INTEGER,                   -- base + adjustment (capped)
    xp_earned       INTEGER DEFAULT 0,
    UNIQUE(student_id, session_date),
    CONSTRAINT valid_r2_status CHECK (status IN ('pending', 'active', 'completed', 'expired'))
);

CREATE INDEX idx_round2_sessions_student_id ON round2_sessions(student_id);
CREATE INDEX idx_round2_sessions_date ON round2_sessions(session_date);

-- Individual questions within a Round 2 session
CREATE TABLE IF NOT EXISTS round2_questions (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER REFERENCES round2_sessions(id),
    question_id     INTEGER REFERENCES questions(id),
    question_order  INTEGER NOT NULL,           -- 1-5
    params          JSONB,
    options         JSONB,
    correct_index   INTEGER,
    answer_index    INTEGER,
    is_correct      BOOLEAN,
    answered_at     TIMESTAMP,
    CONSTRAINT valid_question_order CHECK (question_order BETWEEN 1 AND 5)
);

CREATE INDEX idx_round2_questions_session_id ON round2_questions(session_id);

-- =============================================================================
-- ROUND 3 — PEER CHALLENGES
-- =============================================================================

-- Challenge queue: created after R2, delivered to target
CREATE TABLE IF NOT EXISTS challenge_queue (
    id                      SERIAL PRIMARY KEY,
    sender_id               INTEGER REFERENCES students(id),
    receiver_id             INTEGER REFERENCES students(id),
    session_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    question_id             INTEGER REFERENCES questions(id),
    params                  JSONB,
    options                 JSONB,
    correct_index           INTEGER,
    question_difficulty     INTEGER,                -- final difficulty level
    sender_tier             INTEGER,
    receiver_tier           INTEGER,
    tier_gap                INTEGER,                -- sender_tier - receiver_tier
    is_cross_class          BOOLEAN DEFAULT FALSE,
    source                  TEXT NOT NULL,          -- 'r2_send' or 'r3_forward'
    status                  TEXT DEFAULT 'pending', -- pending, answered, expired
    created_at              TIMESTAMP DEFAULT NOW(),
    expires_at              TIMESTAMP,              -- midnight same day
    CONSTRAINT valid_cq_status CHECK (status IN ('pending', 'answered', 'expired')),
    CONSTRAINT valid_source CHECK (source IN ('r2_send', 'r3_forward'))
);

CREATE INDEX idx_challenge_queue_receiver_id ON challenge_queue(receiver_id);
CREATE INDEX idx_challenge_queue_sender_id ON challenge_queue(sender_id);
CREATE INDEX idx_challenge_queue_session_date ON challenge_queue(session_date);
CREATE INDEX idx_challenge_queue_status ON challenge_queue(status);

-- Responses to challenges
CREATE TABLE IF NOT EXISTS challenge_responses (
    id                  SERIAL PRIMARY KEY,
    challenge_id        INTEGER REFERENCES challenge_queue(id),
    student_id          INTEGER REFERENCES students(id),   -- receiver
    answer_index        INTEGER,
    is_correct          BOOLEAN,
    answered_at         TIMESTAMP DEFAULT NOW(),
    xp_earned           INTEGER DEFAULT 0,
    coins_earned        INTEGER DEFAULT 0,
    consolation_xp      INTEGER DEFAULT 0,                 -- for wrong cross-tier
    class_pride_coins   INTEGER DEFAULT 0,                 -- +5 for cross-class correct
    -- Sender rewards (recorded here for atomicity)
    sender_xp_earned    INTEGER DEFAULT 0,
    UNIQUE(challenge_id, student_id)
);

CREATE INDEX idx_challenge_responses_challenge_id ON challenge_responses(challenge_id);
CREATE INDEX idx_challenge_responses_student_id ON challenge_responses(student_id);

-- =============================================================================
-- SHOP & INVENTORY
-- =============================================================================

CREATE TABLE IF NOT EXISTS shop_items (
    id              SERIAL PRIMARY KEY,
    name_zh         TEXT NOT NULL,
    description_zh  TEXT NOT NULL,
    price           INTEGER NOT NULL,
    category        TEXT NOT NULL,              -- 'ability', 'challenge', 'cosmetic'
    effect_key      TEXT NOT NULL UNIQUE,       -- internal identifier
    max_hold        INTEGER DEFAULT 3,          -- max quantity a student can hold
    is_active       BOOLEAN DEFAULT TRUE,
    CONSTRAINT valid_category CHECK (category IN ('ability', 'challenge', 'cosmetic'))
);

CREATE TABLE IF NOT EXISTS inventory (
    id              SERIAL PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id),
    item_id         INTEGER REFERENCES shop_items(id),
    quantity        INTEGER DEFAULT 0,
    acquired_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE(student_id, item_id)
);

CREATE INDEX idx_inventory_student_id ON inventory(student_id);

-- =============================================================================
-- BADGES
-- =============================================================================

CREATE TABLE IF NOT EXISTS badges (
    id              SERIAL PRIMARY KEY,
    key             TEXT UNIQUE NOT NULL,
    name_zh         TEXT NOT NULL,
    description_zh  TEXT NOT NULL,
    icon            TEXT NOT NULL               -- emoji
);

CREATE TABLE IF NOT EXISTS student_badges (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER REFERENCES students(id),
    badge_key   TEXT NOT NULL,
    earned_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE(student_id, badge_key)
);

CREATE INDEX idx_student_badges_student_id ON student_badges(student_id);

-- =============================================================================
-- LEADERBOARD SNAPSHOTS
-- =============================================================================

-- Nightly snapshot per student (for history and trends)
CREATE TABLE IF NOT EXISTS nightly_snapshots (
    id              SERIAL PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id),
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    xp_earned       INTEGER DEFAULT 0,          -- XP earned this night total
    r1_xp           INTEGER DEFAULT 0,
    r2_xp           INTEGER DEFAULT 0,
    r3_xp           INTEGER DEFAULT 0,
    coins_earned    INTEGER DEFAULT 0,
    rank_num        INTEGER,                    -- rank at end of night
    participated    BOOLEAN DEFAULT FALSE,
    UNIQUE(student_id, snapshot_date)
);

CREATE INDEX idx_nightly_snapshots_student_id ON nightly_snapshots(student_id);
CREATE INDEX idx_nightly_snapshots_date ON nightly_snapshots(snapshot_date);

-- Class vs class weekly stats
CREATE TABLE IF NOT EXISTS class_weekly_stats (
    id              SERIAL PRIMARY KEY,
    class_id        INTEGER REFERENCES classes(id),
    week_start      DATE NOT NULL,              -- Monday of the week
    total_xp        INTEGER DEFAULT 0,
    avg_xp          NUMERIC(8,2) DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,          -- cross-class challenge wins
    losses          INTEGER DEFAULT 0,
    UNIQUE(class_id, week_start)
);

CREATE INDEX idx_class_weekly_stats_week ON class_weekly_stats(week_start);

-- =============================================================================
-- WEEKLY TOURNAMENT
-- =============================================================================

CREATE TABLE IF NOT EXISTS tournaments (
    id              SERIAL PRIMARY KEY,
    grade           TEXT NOT NULL,
    scope           TEXT NOT NULL,              -- 'class' or 'grade'
    class_id        INTEGER REFERENCES classes(id) NULL, -- NULL for grade-wide
    week_start      DATE NOT NULL,
    week_end        DATE NOT NULL,
    status          TEXT DEFAULT 'active',      -- active, completed
    winner_id       INTEGER REFERENCES students(id) NULL,
    second_id       INTEGER REFERENCES students(id) NULL,
    third_id        INTEGER REFERENCES students(id) NULL,
    resolved_at     TIMESTAMP,
    CONSTRAINT valid_scope CHECK (scope IN ('class', 'grade')),
    CONSTRAINT valid_t_status CHECK (status IN ('active', 'completed'))
);

CREATE INDEX idx_tournaments_week ON tournaments(week_start);
CREATE INDEX idx_tournaments_grade ON tournaments(grade);

-- =============================================================================
-- BOSS RAIDS (optional, admin-triggered)
-- =============================================================================

CREATE TABLE IF NOT EXISTS boss_raids (
    id              SERIAL PRIMARY KEY,
    title_zh        TEXT NOT NULL,
    grade           TEXT NOT NULL,
    scope           TEXT NOT NULL,              -- 'class' or 'grade'
    class_id        INTEGER REFERENCES classes(id) NULL,
    question_id     INTEGER REFERENCES questions(id),
    params          JSONB,
    options         JSONB,
    correct_index   INTEGER,
    max_hp          INTEGER NOT NULL,
    current_hp      INTEGER NOT NULL,
    xp_reward       INTEGER DEFAULT 50,
    coins_reward    INTEGER DEFAULT 20,
    starts_at       TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_by      BIGINT                      -- admin telegram_id
);

CREATE INDEX idx_boss_raids_is_active ON boss_raids(is_active);

CREATE TABLE IF NOT EXISTS boss_hits (
    id          SERIAL PRIMARY KEY,
    boss_id     INTEGER REFERENCES boss_raids(id),
    student_id  INTEGER REFERENCES students(id),
    is_correct  BOOLEAN,
    damage      INTEGER DEFAULT 0,
    hit_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(boss_id, student_id)
);

CREATE INDEX idx_boss_hits_boss_id ON boss_hits(boss_id);

-- =============================================================================
-- SEED DATA
-- =============================================================================

-- Classes
INSERT INTO classes (class_code, grade, display_name) VALUES
('P6A', 'P6', '甲班'),
('P6B', 'P6', '乙班'),
('P6C', 'P6', '丙班'),
('P6D', 'P6', '丁班')
ON CONFLICT (class_code) DO NOTHING;

-- Shop items
INSERT INTO shop_items (name_zh, description_zh, price, category, effect_key, max_hold) VALUES
('護盾',     '保護你一次不被挑戰扣XP',                      50,  'ability',   'shield',      3),
('延時券',   '將今晚挑戰期限延至明早8am',                    30,  'ability',   'extension',   2),
('窺探券',   '查看目標同學的Round 2準確率',                  40,  'ability',   'spy',         2),
('重置券',   '重置今晚Round 2題目（只限一次）',               80,  'ability',   'reset',       1),
('雙倍賭注', '你的挑戰若對方答錯，你得雙倍XP',               60,  'challenge', 'double_down', 2),
('指定券',   '強制某同學必須接受你的挑戰',                    20,  'challenge', 'target',      3),
('陷阱券',   '對方答錯你的挑戰時，對方額外失去少量XP',        70,  'challenge', 'trap',        2),
('頭銜框',   '在排行榜名字旁顯示特別頭銜',                   100, 'cosmetic',  'title_frame', 1),
('星級標記', '排行榜顯示特別星級標記',                        80,  'cosmetic',  'star_mark',   1)
ON CONFLICT (effect_key) DO NOTHING;

-- Badges
INSERT INTO badges (key, name_zh, description_zh, icon) VALUES
('first_win',        '初次勝利',   '贏得第一場Round 1對戰',            '⚡'),
('seven_streak',     '七日連勝',   '連續7天參與',                      '🔥'),
('fourteen_streak',  '十四日連勝', '連續14天參與',                     '💎'),
('thirty_streak',    '三十日連勝', '連續30天參與',                     '👑'),
('giant_killer',     '以小勝大',   '答對比你高2個tier的挑戰',          '⚔️'),
('brave_challenger', '勇敢挑戰者', '向高2個tier的同學發出挑戰',        '💪'),
('class_pride',      '班級榮譽',   '贏得5場跨班挑戰',                  '🏫'),
('perfect_r2',       '完美準確',   'Round 2答對全部5題',               '🎯'),
('trap_master',      '陷阱大師',   '成功用陷阱券令3人答錯',            '🪤'),
('sharpshooter',     '神射手',     '連續3晚Round 2 100%準確率',        '🏹'),
('top_class',        '班級之星',   '贏得班級週榜第一',                 '🥇'),
('top_grade',        '全級精英',   '贏得全級週榜第一',                 '🏆'),
('hundred_correct',  '百題達人',   '累計答對100題',                    '💯'),
('night_owl',        '夜貓子',     '午夜前完成所有三輪',               '🦉')
ON CONFLICT (key) DO NOTHING;

-- Topics
INSERT INTO topics (name_en, name_zh, grade, sort_order, is_active) VALUES
('Whole Numbers',        '整數',           'BOTH', 1,  TRUE),
('Fractions Basic',      '分數（基礎）',   'BOTH', 2,  TRUE),
('Fractions Advanced',   '分數（進階）',   'BOTH', 3,  FALSE),
('Decimals',             '小數',           'BOTH', 4,  TRUE),
('Percentages',          '百分數',         'BOTH', 5,  TRUE),
('Ratio',                '比',             'P6',   6,  FALSE),
('Area & Perimeter',     '面積與周界',     'BOTH', 7,  TRUE),
('Speed Distance Time',  '速度距離時間',   'P6',   8,  FALSE),
('Algebra Intro',        '代數入門',       'P6',   9,  FALSE),
('Data & Graphs',        '數據與圖表',     'BOTH', 10, FALSE)
ON CONFLICT DO NOTHING;
