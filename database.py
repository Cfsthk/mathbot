"""
database.py — MathBot MVP v2.0
All asyncpg query functions grouped by domain.
Pool is stored in application.bot_data['db'] at startup.
"""
import asyncpg
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, date
import config

# =============================================================================
# POOL LIFECYCLE
# =============================================================================

async def init_db(application) -> None:
    pool = await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASS,
        min_size=2,
        max_size=15,
        command_timeout=60
    )
    application.bot_data['db'] = pool
    print(f"✅ DB pool ready: {config.DB_NAME}@{config.DB_HOST}")


async def close_db(application) -> None:
    pool = application.bot_data.get('db')
    if pool:
        await pool.close()
        print("✅ DB pool closed")


# =============================================================================
# HELPERS
# =============================================================================

def _row(r) -> Optional[Dict[str, Any]]:
    return dict(r) if r else None

def _rows(rs) -> List[Dict[str, Any]]:
    return [dict(r) for r in rs]


# =============================================================================
# CLASSES
# =============================================================================

async def get_all_classes(pool: asyncpg.Pool, grade: Optional[str] = None) -> List[Dict]:
    async with pool.acquire() as conn:
        if grade:
            rows = await conn.fetch(
                "SELECT * FROM classes WHERE grade = $1 ORDER BY class_code", grade)
        else:
            rows = await conn.fetch("SELECT * FROM classes ORDER BY class_code")
        return _rows(rows)


async def get_class_by_code(pool: asyncpg.Pool, class_code: str) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM classes WHERE class_code = $1", class_code))


async def get_class_by_id(pool: asyncpg.Pool, class_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM classes WHERE id = $1", class_id))


async def set_class_channel(pool: asyncpg.Pool, class_id: int, channel_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE classes SET channel_id = $2 WHERE id = $1",
            class_id, channel_id)


async def get_grade_channel(pool: asyncpg.Pool, grade: str) -> Optional[int]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT channel_id FROM grade_channels WHERE grade = $1", grade)
        return row['channel_id'] if row else None


async def set_grade_channel(pool: asyncpg.Pool, grade: str, channel_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO grade_channels (grade, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (grade) DO UPDATE SET channel_id = $2
            """,
            grade, channel_id)


# =============================================================================
# STUDENTS
# =============================================================================

async def get_student(pool: asyncpg.Pool, telegram_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM students WHERE telegram_id = $1", telegram_id))


async def get_student_by_id(pool: asyncpg.Pool, student_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM students WHERE id = $1", student_id))


async def get_active_students(pool: asyncpg.Pool,
                              grade: Optional[str] = None,
                              class_id: Optional[int] = None) -> List[Dict]:
    async with pool.acquire() as conn:
        query = "SELECT * FROM students WHERE is_active = TRUE"
        params = []
        if grade:
            params.append(grade)
            query += f" AND grade = ${len(params)}"
        if class_id:
            params.append(class_id)
            query += f" AND class_id = ${len(params)}"
        query += " ORDER BY xp DESC"
        return _rows(await conn.fetch(query, *params))


async def get_active_students_by_tier(pool: asyncpg.Pool,
                                      tier: int,
                                      grade: str,
                                      class_id: Optional[int] = None) -> List[Dict]:
    """Used for Round 1 group formation."""
    async with pool.acquire() as conn:
        if class_id:
            rows = await conn.fetch(
                """SELECT * FROM students
                   WHERE is_active = TRUE AND tier = $1
                   AND grade = $2 AND class_id = $3
                   ORDER BY RANDOM()""",
                tier, grade, class_id)
        else:
            rows = await conn.fetch(
                """SELECT * FROM students
                   WHERE is_active = TRUE AND tier = $1 AND grade = $2
                   ORDER BY RANDOM()""",
                tier, grade)
        return _rows(rows)


async def get_pending_students(pool: asyncpg.Pool) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            "SELECT s.*, c.class_code FROM students s "
            "LEFT JOIN classes c ON s.class_id = c.id "
            "WHERE s.is_active = FALSE ORDER BY s.joined_at ASC"))


async def create_student(pool: asyncpg.Pool, telegram_id: int, username: str,
                         display_name: str, class_id: int, grade: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO students (telegram_id, username, display_name, class_id, grade)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            telegram_id, username, display_name, class_id, grade)
        return row['id']


async def approve_student(pool: asyncpg.Pool, student_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE students SET is_active = TRUE WHERE id = $1", student_id)
        return result == "UPDATE 1"


async def update_student_xp_coins(pool: asyncpg.Pool, student_id: int,
                                  xp_delta: int, coins_delta: int) -> Dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE students
               SET xp      = GREATEST(0, xp + $2),
                   coins   = GREATEST(0, coins + $3),
                   weekly_xp = GREATEST(0, weekly_xp + $2)
               WHERE id = $1
               RETURNING xp, coins, weekly_xp""",
            student_id, xp_delta, coins_delta)
        return dict(row) if row else {}


async def update_student_streak(pool: asyncpg.Pool, student_id: int,
                                new_streak: int, last_date: date) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET streak = $2, last_active_date = $3 WHERE id = $1",
            student_id, new_streak, last_date)


async def update_student_rank_tier(pool: asyncpg.Pool, student_id: int,
                                   rank_num: int, tier: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET rank_num = $2, tier = $3 WHERE id = $1",
            student_id, rank_num, tier)


async def reset_nightly_flags(pool: asyncpg.Pool) -> None:
    """Called by scheduler at midnight to reset all per-night counters."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE students SET
               shield_active       = FALSE,
               extension_active    = FALSE,
               double_down_active  = FALSE,
               trap_active         = FALSE,
               spy_used_today      = FALSE,
               r2_sends_tonight    = 0,
               r3_sends_tonight    = 0,
               r3_received_tonight = 0
            """)


async def reset_weekly_xp(pool: asyncpg.Pool) -> None:
    """Called by scheduler every Monday at midnight."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE students SET weekly_xp = 0")


async def get_class_rivals(pool: asyncpg.Pool, student_id: int,
                           rank_window: int = 2) -> List[Dict]:
    """Return students within ±rank_window XP ranks in same class."""
    async with pool.acquire() as conn:
        student = await get_student_by_id(pool, student_id)
        if not student:
            return []
        rows = await conn.fetch(
            """WITH ranked AS (
                 SELECT *, ROW_NUMBER() OVER (ORDER BY xp DESC) AS pos
                 FROM students
                 WHERE class_id = $1 AND is_active = TRUE
               ),
               my_pos AS (SELECT pos FROM ranked WHERE id = $2)
               SELECT r.*
               FROM ranked r, my_pos
               WHERE r.id != $2
               AND ABS(r.pos - my_pos.pos) <= $3
               ORDER BY r.xp DESC""",
            student['class_id'], student_id, rank_window)
        return _rows(rows)


async def get_grade_rivals(pool: asyncpg.Pool, student_id: int,
                           rank_window: int = 2) -> List[Dict]:
    """Return students within ±rank_window XP ranks across whole grade (same tier)."""
    async with pool.acquire() as conn:
        student = await get_student_by_id(pool, student_id)
        if not student:
            return []
        rows = await conn.fetch(
            """WITH ranked AS (
                 SELECT s.*, c.class_code,
                        ROW_NUMBER() OVER (ORDER BY s.xp DESC) AS pos
                 FROM students s
                 JOIN classes c ON s.class_id = c.id
                 WHERE s.grade = $1 AND s.tier = $2 AND s.is_active = TRUE
               ),
               my_pos AS (SELECT pos FROM ranked WHERE id = $3)
               SELECT r.*
               FROM ranked r, my_pos
               WHERE r.id != $3
               AND ABS(r.pos - my_pos.pos) <= $4
               ORDER BY r.xp DESC""",
            student['grade'], student['tier'], student_id, rank_window)
        return _rows(rows)


# =============================================================================
# ITEM FLAGS
# =============================================================================

async def activate_shield(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET shield_active = TRUE WHERE id = $1", student_id)


async def consume_shield(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET shield_active = FALSE WHERE id = $1", student_id)


async def activate_extension(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET extension_active = TRUE WHERE id = $1", student_id)


async def activate_double_down(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET double_down_active = TRUE WHERE id = $1", student_id)


async def consume_double_down(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET double_down_active = FALSE WHERE id = $1", student_id)


async def activate_trap(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET trap_active = TRUE WHERE id = $1", student_id)


async def consume_trap(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET trap_active = FALSE WHERE id = $1", student_id)


async def mark_spy_used(pool: asyncpg.Pool, student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET spy_used_today = TRUE WHERE id = $1", student_id)


# =============================================================================
# QUESTIONS & TOPICS
# =============================================================================

async def get_random_question(pool: asyncpg.Pool,
                              difficulty: Optional[int] = None,
                              grade: Optional[str] = None,
                              diff_min: Optional[int] = None,
                              diff_max: Optional[int] = None) -> Optional[Dict]:
    """
    Flexible question fetcher.
    - difficulty=N           → exact difficulty match
    - diff_min=N, diff_max=M → random within range
    - grade=G                → filter by grade (P5/P6/BOTH)
    Handlers call: get_random_question(pool, grade=grade, diff_min=1, diff_max=5)
    """
    async with pool.acquire() as conn:
        params: list = []
        clauses = [
            "q.is_active = TRUE",
            "t.is_active = TRUE",
        ]

        if grade:
            params.append(grade)
            clauses.append(f"(t.grade = ${len(params)} OR t.grade = 'BOTH')")

        if difficulty is not None:
            params.append(difficulty)
            clauses.append(f"q.difficulty = ${len(params)}")
        elif diff_min is not None and diff_max is not None:
            params.extend([diff_min, diff_max])
            clauses.append(
                f"q.difficulty BETWEEN ${len(params)-1} AND ${len(params)}")

        where = " AND ".join(clauses)
        sql = f"""SELECT q.* FROM questions q
                  JOIN topics t ON q.topic_id = t.id
                  WHERE {where}
                  ORDER BY RANDOM() LIMIT 1"""
        row = await conn.fetchrow(sql, *params)
        return _row(row)


async def get_questions_for_r2(pool: asyncpg.Pool, difficulty: int,
                               grade: str, count: int = 5) -> List[Dict]:
    """Get `count` distinct questions for a Round 2 session."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT q.* FROM questions q
               JOIN topics t ON q.topic_id = t.id
               WHERE q.is_active = TRUE
               AND q.difficulty = $1
               AND t.is_active = TRUE
               AND (t.grade = $2 OR t.grade = 'BOTH')
               ORDER BY RANDOM() LIMIT $3""",
            difficulty, grade, count)
        return _rows(rows)


async def get_question_by_id(pool: asyncpg.Pool, question_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM questions WHERE id = $1", question_id))


async def get_all_topics(pool: asyncpg.Pool, grade: Optional[str] = None) -> List[Dict]:
    async with pool.acquire() as conn:
        if grade:
            rows = await conn.fetch(
                "SELECT * FROM topics WHERE (grade = $1 OR grade = 'BOTH') ORDER BY sort_order",
                grade)
        else:
            rows = await conn.fetch("SELECT * FROM topics ORDER BY sort_order")
        return _rows(rows)


async def toggle_topic(pool: asyncpg.Pool, topic_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE topics SET is_active = NOT is_active WHERE id = $1 RETURNING is_active",
            topic_id)
        return row['is_active'] if row else False


# =============================================================================
# ROUND 1 — BATTLE SESSION
# =============================================================================

async def create_battle_session(pool: asyncpg.Pool, grade: str) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO battle_sessions (grade, status, opened_at)
               VALUES ($1, 'active', NOW())
               ON CONFLICT (session_date, grade) DO UPDATE
               SET status = 'active', opened_at = NOW()
               RETURNING id""",
            grade)
        return row['id']


async def close_battle_session(pool: asyncpg.Pool, session_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE battle_sessions SET status = 'closed', closed_at = NOW() WHERE id = $1",
            session_id)


async def get_todays_battle_session(pool: asyncpg.Pool, grade: str) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            """SELECT * FROM battle_sessions
               WHERE session_date = CURRENT_DATE AND grade = $1""",
            grade))


async def create_battle_group(pool: asyncpg.Pool, session_id: int, tier: int,
                              question_id: int, params: Dict,
                              options: List, correct_index: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO battle_groups
               (session_id, tier, question_id, params, options, correct_index,
                status, opened_at, closed_at)
               VALUES ($1, $2, $3, $4, $5, $6, 'active', NOW(), NOW() + INTERVAL '15 minutes')
               RETURNING id""",
            session_id, tier, question_id,
            json.dumps(params), json.dumps(options), correct_index)
        return row['id']


async def add_battle_group_member(pool: asyncpg.Pool, group_id: int,
                                  student_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO battle_group_members (group_id, student_id)
               VALUES ($1, $2) ON CONFLICT DO NOTHING""",
            group_id, student_id)


async def get_student_battle_group(pool: asyncpg.Pool, student_id: int,
                                   session_id: int) -> Optional[Dict]:
    """Get the battle group a student belongs to for tonight."""
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            """SELECT bg.* FROM battle_groups bg
               JOIN battle_group_members bgm ON bg.id = bgm.group_id
               WHERE bgm.student_id = $1 AND bg.session_id = $2""",
            student_id, session_id))


async def get_battle_group_members(pool: asyncpg.Pool, group_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT bgm.*, s.display_name, s.tier, s.rank_num
               FROM battle_group_members bgm
               JOIN students s ON bgm.student_id = s.id
               WHERE bgm.group_id = $1
               ORDER BY bgm.answered_at ASC NULLS LAST""",
            group_id))


async def record_battle_answer(pool: asyncpg.Pool, group_id: int,
                               student_id: int, answer_index: int,
                               is_correct: bool) -> int:
    """Record answer and return finish_position (1st, 2nd, etc correct)."""
    async with pool.acquire() as conn:
        if is_correct:
            pos_row = await conn.fetchrow(
                """SELECT COUNT(*) + 1 AS pos FROM battle_group_members
                   WHERE group_id = $1 AND is_correct = TRUE""",
                group_id)
            position = pos_row['pos']
        else:
            position = None

        await conn.execute(
            """UPDATE battle_group_members
               SET answer_index = $3, is_correct = $4,
                   answered_at = NOW(), finish_position = $5
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id, answer_index, is_correct, position)
        return position


async def set_battle_group_winner(pool: asyncpg.Pool, group_id: int,
                                  winner_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE battle_groups SET winner_id = $2 WHERE id = $1",
            group_id, winner_id)


async def record_battle_rewards(pool: asyncpg.Pool, group_id: int,
                                student_id: int, xp: int, coins: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE battle_group_members
               SET xp_earned = $3, coins_earned = $4
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id, xp, coins)


async def close_battle_group(pool: asyncpg.Pool, group_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE battle_groups SET status = 'closed', closed_at = NOW() WHERE id = $1",
            group_id)


async def get_open_battle_groups(pool: asyncpg.Pool, session_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT * FROM battle_groups
               WHERE session_id = $1 AND status = 'active'
               AND closed_at <= NOW()""",
            session_id))


async def student_already_answered_battle(pool: asyncpg.Pool, group_id: int,
                                          student_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT answer_index FROM battle_group_members
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id)
        return row is not None and row['answer_index'] is not None


# =============================================================================
# ROUND 2 — SOLO SESSION
# =============================================================================

async def create_round2_session(pool: asyncpg.Pool, student_id: int,
                                difficulty_base: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO round2_sessions
               (student_id, status, started_at, difficulty_base, final_difficulty)
               VALUES ($1, 'active', NOW(), $2, $2)
               ON CONFLICT (student_id, session_date) DO UPDATE
               SET status = 'active', started_at = NOW()
               RETURNING id""",
            student_id, difficulty_base)
        return row['id']


async def get_todays_round2_session(pool: asyncpg.Pool,
                                    student_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            """SELECT * FROM round2_sessions
               WHERE student_id = $1 AND session_date = CURRENT_DATE""",
            student_id))


async def add_round2_question(pool: asyncpg.Pool, session_id: int,
                              question_id: int, order: int,
                              params: Dict, options: List,
                              correct_index: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO round2_questions
               (session_id, question_id, question_order, params, options, correct_index)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            session_id, question_id, order,
            json.dumps(params), json.dumps(options), correct_index)
        return row['id']


async def get_round2_questions(pool: asyncpg.Pool, session_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT * FROM round2_questions
               WHERE session_id = $1 ORDER BY question_order""",
            session_id))


async def record_round2_answer(pool: asyncpg.Pool, r2q_id: int,
                               answer_index: int, is_correct: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_questions
               SET answer_index = $2, is_correct = $3, answered_at = NOW()
               WHERE id = $1""",
            r2q_id, answer_index, is_correct)


async def complete_round2_session(pool: asyncpg.Pool, session_id: int,
                                  correct_count: int, accuracy: float,
                                  difficulty_adjustment: int,
                                  final_difficulty: int,
                                  xp_earned: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_sessions
               SET status = 'completed', completed_at = NOW(),
                   correct_count = $2, accuracy = $3,
                   difficulty_adjustment = $4, final_difficulty = $5,
                   xp_earned = $6
               WHERE id = $1""",
            session_id, correct_count, accuracy,
            difficulty_adjustment, final_difficulty, xp_earned)


async def expire_round2_sessions(pool: asyncpg.Pool) -> None:
    """Called at 10pm — mark all incomplete sessions as expired."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_sessions
               SET status = 'expired', completed_at = NOW()
               WHERE status = 'active'
               AND session_date = CURRENT_DATE""")


async def reset_round2_session(pool: asyncpg.Pool, student_id: int,
                               new_difficulty: int) -> int:
    """Used by 重置券 shop item — delete questions, reset session."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM round2_sessions WHERE student_id = $1 AND session_date = CURRENT_DATE",
            student_id)
        if not row:
            return 0
        session_id = row['id']
        await conn.execute(
            "DELETE FROM round2_questions WHERE session_id = $1", session_id)
        await conn.execute(
            """UPDATE round2_sessions
               SET correct_count = 0, accuracy = NULL,
                   difficulty_base = $2, final_difficulty = $2,
                   difficulty_adjustment = 0, status = 'active'
               WHERE id = $1""",
            session_id, new_difficulty)
        return session_id


# =============================================================================
# ROUND 3 — CHALLENGE QUEUE
# =============================================================================

async def create_challenge(pool: asyncpg.Pool, sender_id: int,
                           receiver_id: int, question_id: int,
                           params: Dict, options: List, correct_index: int,
                           question_difficulty: int, sender_tier: int,
                           receiver_tier: int, is_cross_class: bool,
                           source: str) -> int:
    """source: 'r2_send' or 'r3_forward'"""
    # Expire at midnight HKT same day (stored as UTC)
    expires_at = datetime.utcnow().replace(hour=16, minute=0, second=0, microsecond=0)
    # If already past 16:00 UTC (midnight HKT), expire tomorrow
    if datetime.utcnow() > expires_at:
        expires_at += timedelta(days=1)

    tier_gap = sender_tier - receiver_tier

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO challenge_queue
               (sender_id, receiver_id, question_id, params, options, correct_index,
                question_difficulty, sender_tier, receiver_tier, tier_gap,
                is_cross_class, source, expires_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
               RETURNING id""",
            sender_id, receiver_id, question_id,
            json.dumps(params), json.dumps(options), correct_index,
            question_difficulty, sender_tier, receiver_tier, tier_gap,
            is_cross_class, source, expires_at)

        # Increment receiver's received count and sender's send count
        await conn.execute(
            "UPDATE students SET r3_received_tonight = r3_received_tonight + 1 WHERE id = $1",
            receiver_id)
        if source == 'r2_send':
            await conn.execute(
                "UPDATE students SET r2_sends_tonight = r2_sends_tonight + 1 WHERE id = $1",
                sender_id)
        else:
            await conn.execute(
                "UPDATE students SET r3_sends_tonight = r3_sends_tonight + 1 WHERE id = $1",
                sender_id)

        return row['id']


async def get_pending_challenges(pool: asyncpg.Pool,
                                 student_id: int) -> List[Dict]:
    """Get all pending challenges for a student tonight."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT cq.*, s.display_name AS sender_name,
                      s.tier AS sender_tier_val,
                      c.class_code AS sender_class
               FROM challenge_queue cq
               JOIN students s ON cq.sender_id = s.id
               LEFT JOIN classes c ON s.class_id = c.id
               WHERE cq.receiver_id = $1
               AND cq.status = 'pending'
               AND cq.expires_at > NOW()
               ORDER BY cq.created_at ASC""",
            student_id))


async def get_challenge_by_id(pool: asyncpg.Pool, challenge_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM challenge_queue WHERE id = $1", challenge_id))


async def record_challenge_response(pool: asyncpg.Pool, challenge_id: int,
                                    student_id: int, answer_index: int,
                                    is_correct: bool, xp_earned: int,
                                    coins_earned: int, consolation_xp: int,
                                    class_pride_coins: int,
                                    sender_xp_earned: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO challenge_responses
               (challenge_id, student_id, answer_index, is_correct,
                xp_earned, coins_earned, consolation_xp,
                class_pride_coins, sender_xp_earned)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (challenge_id, student_id) DO NOTHING""",
            challenge_id, student_id, answer_index, is_correct,
            xp_earned, coins_earned, consolation_xp,
            class_pride_coins, sender_xp_earned)
        await conn.execute(
            "UPDATE challenge_queue SET status = 'answered' WHERE id = $1",
            challenge_id)


async def expire_old_challenges(pool: asyncpg.Pool) -> int:
    """Called at midnight — expire all unanswered challenges."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE challenge_queue SET status = 'expired'
               WHERE status = 'pending' AND expires_at <= NOW()""")
        return int(result.split()[-1])


async def can_send_challenge(pool: asyncpg.Pool, sender_id: int,
                             source: str) -> bool:
    """Check if sender still has send slots tonight."""
    student = await get_student_by_id(pool, sender_id)
    if not student:
        return False
    if source == 'r2_send':
        return student['r2_sends_tonight'] < 1
    else:  # r3_forward
        return student['r3_sends_tonight'] < 1


async def can_receive_challenge(pool: asyncpg.Pool, receiver_id: int) -> bool:
    student = await get_student_by_id(pool, receiver_id)
    if not student:
        return False
    return student['r3_received_tonight'] < config.MAX_CHALLENGES_RECEIVED


async def get_valid_r3_targets(pool: asyncpg.Pool, sender_id: int,
                               cross_class: bool = False) -> List[Dict]:
    """
    Return classmates (or grade peers) at same tier who can still receive
    a challenge tonight and haven't been targeted by this sender already.
    """
    student = await get_student_by_id(pool, sender_id)
    if not student:
        return []
    async with pool.acquire() as conn:
        if cross_class:
            rows = await conn.fetch(
                """SELECT s.id, s.display_name, s.tier, s.rank_num,
                          c.class_code
                   FROM students s
                   JOIN classes c ON s.class_id = c.id
                   WHERE s.grade = $1 AND s.tier = $2
                   AND s.is_active = TRUE AND s.id != $3
                   AND s.r3_received_tonight < $4
                   AND s.id NOT IN (
                       SELECT receiver_id FROM challenge_queue
                       WHERE sender_id = $3
                       AND session_date = CURRENT_DATE
                   )
                   ORDER BY s.display_name""",
                student['grade'], student['tier'],
                sender_id, config.MAX_CHALLENGES_RECEIVED)
        else:
            rows = await conn.fetch(
                """SELECT s.id, s.display_name, s.tier, s.rank_num
                   FROM students s
                   WHERE s.class_id = $1 AND s.tier = $2
                   AND s.is_active = TRUE AND s.id != $3
                   AND s.r3_received_tonight < $4
                   AND s.id NOT IN (
                       SELECT receiver_id FROM challenge_queue
                       WHERE sender_id = $3
                       AND session_date = CURRENT_DATE
                   )
                   ORDER BY s.display_name""",
                student['class_id'], student['tier'],
                sender_id, config.MAX_CHALLENGES_RECEIVED)
        return _rows(rows)


# =============================================================================
# SHOP & INVENTORY
# =============================================================================

async def get_shop_items(pool: asyncpg.Pool,
                         category: Optional[str] = None) -> List[Dict]:
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                "SELECT * FROM shop_items WHERE is_active = TRUE AND category = $1",
                category)
        else:
            rows = await conn.fetch(
                "SELECT * FROM shop_items WHERE is_active = TRUE ORDER BY category, price")
        return _rows(rows)


async def get_shop_item_by_key(pool: asyncpg.Pool,
                               effect_key: str) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM shop_items WHERE effect_key = $1", effect_key))


async def get_inventory(pool: asyncpg.Pool, student_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT i.quantity, si.name_zh, si.description_zh,
                      si.effect_key, si.category, si.max_hold
               FROM inventory i
               JOIN shop_items si ON i.item_id = si.id
               WHERE i.student_id = $1 AND i.quantity > 0
               ORDER BY si.category, si.price""",
            student_id))


async def get_inventory_item(pool: asyncpg.Pool, student_id: int,
                             effect_key: str) -> Optional[Dict]:
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            """SELECT i.quantity, si.* FROM inventory i
               JOIN shop_items si ON i.item_id = si.id
               WHERE i.student_id = $1 AND si.effect_key = $2""",
            student_id, effect_key))


async def purchase_item(pool: asyncpg.Pool,
                        student_id: int,
                        effect_key: Optional[str] = None,
                        item_key: Optional[str] = None,
                        price: Optional[int] = None) -> bool:
    """
    Attempt purchase. Returns True on success.
    Accepts effect_key= or item_key= (shop handler uses item_key=).
    Atomic: deducts coins and increments inventory in one transaction.
    Full result available via _purchase_item_full().
    """
    key = item_key or effect_key
    result = await _purchase_item_full(pool, student_id, key)
    return result.get('ok', False)


async def consume_item(pool: asyncpg.Pool, student_id: int,
                       effect_key: str) -> bool:
    """Decrement inventory by 1. Returns True if consumed."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            item = await conn.fetchrow(
                "SELECT id FROM shop_items WHERE effect_key = $1", effect_key)
            if not item:
                return False
            row = await conn.fetchrow(
                """UPDATE inventory SET quantity = quantity - 1
                   WHERE student_id = $1 AND item_id = $2 AND quantity > 0
                   RETURNING quantity""",
                student_id, item['id'])
            return row is not None


# =============================================================================
# BADGES
# =============================================================================

async def award_badge(pool: asyncpg.Pool, student_id: int,
                      badge_key: str) -> bool:
    """Returns True if newly awarded."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """INSERT INTO student_badges (student_id, badge_key)
               VALUES ($1, $2) ON CONFLICT DO NOTHING""",
            student_id, badge_key)
        return result == "INSERT 0 1"


async def get_student_badges(pool: asyncpg.Pool, student_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT b.key, b.name_zh, b.description_zh, b.icon, sb.earned_at
               FROM student_badges sb
               JOIN badges b ON sb.badge_key = b.key
               WHERE sb.student_id = $1
               ORDER BY sb.earned_at DESC""",
            student_id))


async def has_badge(pool: asyncpg.Pool, student_id: int,
                    badge_key: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM student_badges WHERE student_id = $1 AND badge_key = $2",
            student_id, badge_key)
        return row is not None


# =============================================================================
# RANK & TIER
# =============================================================================

async def check_and_update_rank(pool: asyncpg.Pool,
                                student_id: int) -> Optional[Dict]:
    """
    Check if student qualifies for a rank/tier change.
    Returns new rank info dict if changed, else None.
    """
    student = await get_student_by_id(pool, student_id)
    if not student:
        return None

    current_xp = student['xp']
    current_rank = student['rank_num']
    new_rank = 1
    new_tier = 1

    for tier_cfg in reversed(config.RANK_TIERS):
        if current_xp >= tier_cfg['xp_required']:
            new_rank = tier_cfg['rank']
            new_tier = tier_cfg['tier']
            break

    if new_rank > current_rank:
        await update_student_rank_tier(pool, student_id, new_rank, new_tier)
        return next(t for t in config.RANK_TIERS if t['rank'] == new_rank)

    return None


# =============================================================================
# LEADERBOARDS
# =============================================================================

async def get_class_leaderboard_tonight(pool: asyncpg.Pool,
                                        class_id: int) -> List[Dict]:
    """Tonight's XP earned per student in a class."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT s.id, s.display_name, s.rank_num, s.tier,
                      COALESCE(ns.xp_earned, 0) AS tonight_xp,
                      COALESCE(ns.r1_xp, 0) AS r1_xp,
                      COALESCE(ns.r2_xp, 0) AS r2_xp,
                      COALESCE(ns.r3_xp, 0) AS r3_xp,
                      COALESCE(ns.participated, FALSE) AS participated
               FROM students s
               LEFT JOIN nightly_snapshots ns
                 ON s.id = ns.student_id AND ns.snapshot_date = CURRENT_DATE
               WHERE s.class_id = $1 AND s.is_active = TRUE
               ORDER BY tonight_xp DESC""",
            class_id))


async def get_grade_leaderboard_weekly(pool: asyncpg.Pool,
                                       grade: str) -> List[Dict]:
    """Grade-wide weekly XP leaderboard."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT s.id, s.display_name, s.rank_num, s.tier,
                      s.weekly_xp, c.class_code, c.display_name AS class_name
               FROM students s
               JOIN classes c ON s.class_id = c.id
               WHERE s.grade = $1 AND s.is_active = TRUE
               ORDER BY s.weekly_xp DESC
               LIMIT 120""",
            grade))


async def get_class_leaderboard_weekly(pool: asyncpg.Pool,
                                       class_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT s.id, s.display_name, s.rank_num, s.tier, s.weekly_xp
               FROM students s
               WHERE s.class_id = $1 AND s.is_active = TRUE
               ORDER BY s.weekly_xp DESC""",
            class_id))


async def get_class_vs_class_leaderboard(pool: asyncpg.Pool,
                                         grade: str) -> List[Dict]:
    """Class vs class by average weekly XP."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT c.id, c.class_code, c.display_name,
                      ROUND(AVG(s.weekly_xp), 1) AS avg_xp,
                      COUNT(s.id) AS student_count,
                      SUM(s.weekly_xp) AS total_xp
               FROM classes c
               LEFT JOIN students s ON s.class_id = c.id AND s.is_active = TRUE
               WHERE c.grade = $1
               GROUP BY c.id, c.class_code, c.display_name
               ORDER BY avg_xp DESC""",
            grade))


async def get_alltime_leaderboard(pool: asyncpg.Pool,
                                  grade: str,
                                  limit: int = 30) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT s.id, s.display_name, s.rank_num, s.tier,
                      s.xp, s.streak, c.class_code
               FROM students s
               JOIN classes c ON s.class_id = c.id
               WHERE s.grade = $1 AND s.is_active = TRUE
               ORDER BY s.xp DESC LIMIT $2""",
            grade, limit))


# =============================================================================
# NIGHTLY SNAPSHOTS
# =============================================================================

async def upsert_nightly_snapshot(pool: asyncpg.Pool, student_id: int,
                                  r1_xp: int, r2_xp: int, r3_xp: int,
                                  coins_earned: int, rank_num: int,
                                  participated: bool) -> None:
    xp_total = r1_xp + r2_xp + r3_xp
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO nightly_snapshots
               (student_id, xp_earned, r1_xp, r2_xp, r3_xp,
                coins_earned, rank_num, participated)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (student_id, snapshot_date) DO UPDATE
               SET xp_earned    = nightly_snapshots.xp_earned + $2,
                   r1_xp        = nightly_snapshots.r1_xp + $3,
                   r2_xp        = nightly_snapshots.r2_xp + $4,
                   r3_xp        = nightly_snapshots.r3_xp + $5,
                   coins_earned = nightly_snapshots.coins_earned + $6,
                   rank_num     = $7,
                   participated = $8""",
            student_id, xp_total, r1_xp, r2_xp, r3_xp,
            coins_earned, rank_num, participated)


async def get_student_history(pool: asyncpg.Pool,
                              student_id: int, days: int = 7) -> List[Dict]:
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT * FROM nightly_snapshots
               WHERE student_id = $1
               ORDER BY snapshot_date DESC LIMIT $2""",
            student_id, days))


# =============================================================================
# WEEKLY TOURNAMENT
# =============================================================================

async def create_weekly_tournaments(pool: asyncpg.Pool, grade: str,
                                    week_start: date, week_end: date) -> None:
    """Create one grade-wide + four class-level tournament records."""
    async with pool.acquire() as conn:
        # Grade-wide
        await conn.execute(
            """INSERT INTO tournaments (grade, scope, week_start, week_end)
               VALUES ($1, 'grade', $2, $3) ON CONFLICT DO NOTHING""",
            grade, week_start, week_end)
        # Per class
        classes = await get_all_classes(pool, grade)
        for cls in classes:
            await conn.execute(
                """INSERT INTO tournaments (grade, scope, class_id, week_start, week_end)
                   VALUES ($1, 'class', $2, $3, $4) ON CONFLICT DO NOTHING""",
                grade, cls['id'], week_start, week_end)


async def resolve_weekly_tournaments(pool: asyncpg.Pool, grade: str,
                                     week_start: date) -> List[Dict]:
    """
    At Sunday midnight: find top 3 per tournament, award prizes, mark completed.
    Returns list of resolved tournament dicts with winner info.
    """
    async with pool.acquire() as conn:
        tournaments = await conn.fetch(
            """SELECT * FROM tournaments
               WHERE grade = $1 AND week_start = $2 AND status = 'active'""",
            grade, week_start)

        results = []
        for t in tournaments:
            if t['scope'] == 'grade':
                top = await conn.fetch(
                    """SELECT id, weekly_xp FROM students
                       WHERE grade = $1 AND is_active = TRUE
                       ORDER BY weekly_xp DESC LIMIT 3""",
                    grade)
            else:
                top = await conn.fetch(
                    """SELECT id, weekly_xp FROM students
                       WHERE class_id = $1 AND is_active = TRUE
                       ORDER BY weekly_xp DESC LIMIT 3""",
                    t['class_id'])

            winner_id  = top[0]['id'] if len(top) > 0 else None
            second_id  = top[1]['id'] if len(top) > 1 else None
            third_id   = top[2]['id'] if len(top) > 2 else None

            prizes = (config.TOURNAMENT_PRIZES_GRADE
                      if t['scope'] == 'grade'
                      else config.TOURNAMENT_PRIZES_CLASS)

            if winner_id:
                await conn.execute(
                    "UPDATE students SET coins = coins + $2 WHERE id = $1",
                    winner_id, prizes[0])
            if second_id:
                await conn.execute(
                    "UPDATE students SET coins = coins + $2 WHERE id = $1",
                    second_id, prizes[1])
            if third_id:
                await conn.execute(
                    "UPDATE students SET coins = coins + $2 WHERE id = $1",
                    third_id, prizes[2])

            await conn.execute(
                """UPDATE tournaments
                   SET status = 'completed', resolved_at = NOW(),
                       winner_id = $2, second_id = $3, third_id = $4
                   WHERE id = $1""",
                t['id'], winner_id, second_id, third_id)

            results.append({
                'scope': t['scope'],
                'class_id': t['class_id'],
                'winner_id': winner_id,
                'second_id': second_id,
                'third_id': third_id,
            })

        return results


# =============================================================================
# STATISTICS (ADMIN)
# =============================================================================

async def get_grade_stats(pool: asyncpg.Pool, grade: str) -> Dict:
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM students WHERE grade = $1 AND is_active = TRUE", grade)
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM students WHERE grade = $1 AND is_active = FALSE", grade)
        participated_tonight = await conn.fetchval(
            """SELECT COUNT(*) FROM nightly_snapshots
               WHERE snapshot_date = CURRENT_DATE AND participated = TRUE
               AND student_id IN (
                   SELECT id FROM students WHERE grade = $1 AND is_active = TRUE
               )""", grade)
        return {
            'total_students': total or 0,
            'pending_approvals': pending or 0,
            'participated_tonight': participated_tonight or 0,
        }


async def get_student_full_stats(pool: asyncpg.Pool,
                                 student_id: int) -> Optional[Dict]:
    """Full profile for /stats command."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT s.*, c.class_code, c.display_name AS class_name,
                      (SELECT COUNT(*) FROM challenge_responses cr
                       JOIN challenge_queue cq ON cr.challenge_id = cq.id
                       WHERE cq.receiver_id = s.id AND cr.is_correct = TRUE
                      ) AS r3_correct,
                      (SELECT COUNT(*) FROM challenge_responses cr
                       JOIN challenge_queue cq ON cr.challenge_id = cq.id
                       WHERE cq.receiver_id = s.id
                      ) AS r3_total,
                      (SELECT COUNT(*) FROM nightly_snapshots
                       WHERE student_id = s.id AND participated = TRUE
                      ) AS total_participations
               FROM students s
               JOIN classes c ON s.class_id = c.id
               WHERE s.id = $1""",
            student_id)
        return _row(row)


# =============================================================================
# ALIASES & MISSING STUDENT FUNCTIONS
# =============================================================================

async def get_student_by_telegram_id(pool: asyncpg.Pool, telegram_id: int) -> Optional[Dict]:
    """Alias for get_student — used by all handlers."""
    return await get_student(pool, telegram_id)


async def get_active_students_with_class(pool: asyncpg.Pool,
                                         grade: Optional[str] = None) -> List[Dict]:
    """Active students joined with class_code — used by Round 1 group formation."""
    async with pool.acquire() as conn:
        if grade:
            rows = await conn.fetch(
                """SELECT s.*, c.class_code, c.display_name AS class_name
                   FROM students s
                   JOIN classes c ON s.class_id = c.id
                   WHERE s.is_active = TRUE AND s.grade = $1
                   ORDER BY s.tier, s.xp DESC""",
                grade)
        else:
            rows = await conn.fetch(
                """SELECT s.*, c.class_code, c.display_name AS class_name
                   FROM students s
                   JOIN classes c ON s.class_id = c.id
                   WHERE s.is_active = TRUE
                   ORDER BY s.tier, s.xp DESC""")
        return _rows(rows)


async def get_active_classmates(pool: asyncpg.Pool,
                                student_id: int,
                                class_id: int) -> List[Dict]:
    """All active classmates excluding the student — used by shop spy picker."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, display_name, rank_num, tier, xp
               FROM students
               WHERE class_id = $1 AND is_active = TRUE AND id != $2
               ORDER BY display_name""",
            class_id, student_id)
        return _rows(rows)


async def get_nearby_students(pool: asyncpg.Pool,
                              student_id: int,
                              window: int = 5) -> List[Dict]:
    """Students within ±window XP rank positions in same grade — for /rivals and challenge."""
    async with pool.acquire() as conn:
        student = await get_student_by_id(pool, student_id)
        if not student:
            return []
        rows = await conn.fetch(
            """WITH ranked AS (
                 SELECT s.*, c.class_code,
                        ROW_NUMBER() OVER (PARTITION BY s.grade ORDER BY s.xp DESC) AS pos
                 FROM students s
                 JOIN classes c ON s.class_id = c.id
                 WHERE s.grade = $1 AND s.is_active = TRUE
               ),
               my_pos AS (SELECT pos FROM ranked WHERE id = $2)
               SELECT r.*
               FROM ranked r, my_pos
               WHERE r.id != $2
               AND ABS(r.pos - my_pos.pos) <= $3
               ORDER BY r.xp DESC""",
            student['grade'], student_id, window)
        return _rows(rows)


async def get_student_rank_position(pool: asyncpg.Pool,
                                    student_id: int,
                                    grade: str) -> int:
    """1-based rank position within grade by XP."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT COUNT(*) + 1 AS pos
               FROM students
               WHERE grade = $1 AND is_active = TRUE
               AND xp > (SELECT xp FROM students WHERE id = $2)""",
            grade, student_id)
        return int(row['pos']) if row else 1


async def reset_nightly_student_flags(pool: asyncpg.Pool) -> None:
    """Alias for reset_nightly_flags — called by nightly.py."""
    await reset_nightly_flags(pool)


# =============================================================================
# APPLY XP & COINS (central reward function)
# =============================================================================

async def apply_xp_and_coins(pool: asyncpg.Pool,
                              student_id: int,
                              xp: int,
                              coins: int,
                              source: str = 'unknown') -> tuple:
    """
    Apply XP and coin delta, check for rank-up.
    Returns (new_xp, leveled_up: bool, new_rank_info: Optional[Dict]).
    Used by round1, round2, round3 handlers.
    """
    updated = await update_student_xp_coins(pool, student_id, xp, coins)
    new_xp = updated.get('xp', 0)

    rank_info = await check_and_update_rank(pool, student_id)
    leveled_up = rank_info is not None

    return new_xp, leveled_up, rank_info


# =============================================================================
# ROUND 1 — MISSING FUNCTIONS
# =============================================================================

async def upsert_battle_session(pool: asyncpg.Pool, grade: str,
                                 session_date: Optional[date] = None) -> int:
    """Create or return today's battle session for a grade."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO battle_sessions (grade, status, session_date, opened_at)
               VALUES ($1, 'active', COALESCE($2, CURRENT_DATE), NOW())
               ON CONFLICT (session_date, grade) DO UPDATE
                 SET status = 'active', opened_at = NOW()
               RETURNING id""",
            grade, session_date)
        return row['id']


async def get_battle_group(pool: asyncpg.Pool, group_id: int) -> Optional[Dict]:
    """Get a battle group by id."""
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM battle_groups WHERE id = $1", group_id))


async def get_battle_group_member(pool: asyncpg.Pool,
                                  group_id: int,
                                  student_id: int) -> Optional[Dict]:
    """Get a single member row from battle_group_members."""
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            """SELECT * FROM battle_group_members
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id))


async def set_group_member_dm_message(pool: asyncpg.Pool,
                                      group_id: int,
                                      student_id: int,
                                      message_id: int) -> None:
    """Store the DM message_id sent to a group member (for later editing)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE battle_group_members
               SET dm_message_id = $3
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id, message_id)


async def claim_next_finish_position(pool: asyncpg.Pool, group_id: int) -> int:
    """Atomically claim the next correct-answer finish position (1st, 2nd, 3rd)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT COALESCE(MAX(finish_position), 0) + 1 AS next_pos
               FROM battle_group_members
               WHERE group_id = $1 AND is_correct = TRUE""",
            group_id)
        return int(row['next_pos']) if row else 1


async def record_r1_answer(pool: asyncpg.Pool,
                            group_id: int,
                            student_id: int,
                            answer_index: int,
                            is_correct: bool,
                            finish_position: Optional[int] = None,
                            xp_earned: int = 0,
                            coins_earned: int = 0) -> None:
    """Record a Round 1 answer on battle_group_members."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE battle_group_members
               SET answer_index    = $3,
                   is_correct      = $4,
                   answered_at     = NOW(),
                   finish_position = $5,
                   xp_earned       = $6,
                   coins_earned    = $7
               WHERE group_id = $1 AND student_id = $2""",
            group_id, student_id, answer_index, is_correct,
            finish_position, xp_earned, coins_earned)


async def check_group_fully_answered(pool: asyncpg.Pool, group_id: int) -> bool:
    """Return True if every member of the group has answered."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT COUNT(*) FILTER (WHERE answer_index IS NULL) AS unanswered
               FROM battle_group_members
               WHERE group_id = $1""",
            group_id)
        return row['unanswered'] == 0 if row else False


async def get_unanswered_group_members(pool: asyncpg.Pool,
                                       group_id: int) -> List[Dict]:
    """Return members who haven't answered yet."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT bgm.*, s.telegram_id, s.display_name
               FROM battle_group_members bgm
               JOIN students s ON bgm.student_id = s.id
               WHERE bgm.group_id = $1 AND bgm.answer_index IS NULL""",
            group_id))


async def get_battle_group_members_with_details(pool: asyncpg.Pool,
                                                group_id: int) -> List[Dict]:
    """Members with full student + class details for results display."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT bgm.*,
                      s.display_name, s.telegram_id, s.tier, s.rank_num, s.xp,
                      c.class_code
               FROM battle_group_members bgm
               JOIN students s ON bgm.student_id = s.id
               LEFT JOIN classes c ON s.class_id = c.id
               WHERE bgm.group_id = $1
               ORDER BY bgm.finish_position ASC NULLS LAST, bgm.answered_at ASC""",
            group_id))


# =============================================================================
# ROUND 2 — MISSING FUNCTIONS
# =============================================================================

async def create_r2_session(pool: asyncpg.Pool,
                             student_id: int,
                             difficulty_base: int,
                             difficulty_adjustment: int = 0) -> int:
    """Create a Round 2 session (alias with adjustment param)."""
    final_diff = max(1, min(10, difficulty_base + difficulty_adjustment))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO round2_sessions
               (student_id, status, started_at, difficulty_base,
                difficulty_adjustment, final_difficulty)
               VALUES ($1, 'active', NOW(), $2, $3, $4)
               ON CONFLICT (student_id, session_date) DO UPDATE
                 SET status = 'active', started_at = NOW(),
                     difficulty_base = $2,
                     difficulty_adjustment = $3,
                     final_difficulty = $4
               RETURNING id""",
            student_id, difficulty_base, difficulty_adjustment, final_diff)
        return row['id']


async def get_r2_session(pool: asyncpg.Pool, session_id: int) -> Optional[Dict]:
    """Get a Round 2 session by id."""
    async with pool.acquire() as conn:
        return _row(await conn.fetchrow(
            "SELECT * FROM round2_sessions WHERE id = $1", session_id))


async def set_r2_session_question(pool: asyncpg.Pool,
                                  session_id: int,
                                  question_id: int,
                                  q_index: int,
                                  params: Dict,
                                  options: List,
                                  correct_index: int) -> int:
    """Insert the next question into round2_questions, return its id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO round2_questions
               (session_id, question_id, question_order, params, options, correct_index)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            session_id, question_id, q_index,
            json.dumps(params), json.dumps(options), correct_index)
        return row['id'] if row else 0


async def set_r2_session_current_message(pool: asyncpg.Pool,
                                         session_id: int,
                                         message_id: int) -> None:
    """Store the current Telegram message_id on the session (for editing)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE round2_sessions SET current_message_id = $2 WHERE id = $1",
            session_id, message_id)


async def advance_r2_session(pool: asyncpg.Pool,
                              session_id: int,
                              is_correct: bool,
                              xp_gained: int) -> tuple:
    """
    Record answer result, increment q_index.
    Returns (new_q_index, correct_count, accumulated_xp).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Get current state
            row = await conn.fetchrow(
                """SELECT correct_count,
                          (SELECT COUNT(*) FROM round2_questions
                           WHERE session_id = $1) AS q_index,
                          xp_earned
                   FROM round2_sessions WHERE id = $1""",
                session_id)
            correct_count = (row['correct_count'] or 0) + (1 if is_correct else 0)
            new_q_index   = int(row['q_index'] or 0)
            xp_acc        = (row['xp_earned'] or 0) + xp_gained

            await conn.execute(
                """UPDATE round2_sessions
                   SET correct_count = $2, xp_earned = $3
                   WHERE id = $1""",
                session_id, correct_count, xp_acc)

            return new_q_index, correct_count, xp_acc


async def close_r2_session(pool: asyncpg.Pool,
                            session_id: int,
                            xp_earned: int,
                            coins_earned: int) -> None:
    """Mark a Round 2 session completed."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_sessions
               SET status = 'completed', completed_at = NOW(),
                   xp_earned = $2
               WHERE id = $1""",
            session_id, xp_earned)


async def get_open_r2_sessions(pool: asyncpg.Pool) -> List[Dict]:
    """Active R2 sessions for tonight's timeout sweep."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT * FROM round2_sessions
               WHERE status = 'active' AND session_date = CURRENT_DATE"""))


async def get_challengeable_classmates(pool: asyncpg.Pool,
                                       student_id: int,
                                       class_id: int,
                                       grade: str) -> List[Dict]:
    """
    Classmates (same class, same tier) who can still receive a challenge tonight.
    Excludes self and anyone already targeted by this sender today.
    """
    student = await get_student_by_id(pool, student_id)
    if not student:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.id, s.display_name, s.tier, s.rank_num
               FROM students s
               WHERE s.class_id = $1
               AND s.tier = $2
               AND s.is_active = TRUE
               AND s.id != $3
               AND s.r3_received_tonight < $4
               AND s.id NOT IN (
                   SELECT receiver_id FROM challenge_queue
                   WHERE sender_id = $3 AND session_date = CURRENT_DATE
               )
               ORDER BY s.display_name""",
            class_id, student['tier'], student_id, config.MAX_CHALLENGES_RECEIVED)
        return _rows(rows)


# =============================================================================
# ROUND 3 — MISSING FUNCTIONS
# =============================================================================

async def create_r3_challenge(pool: asyncpg.Pool,
                               challenger_id: int,
                               defender_id: int,
                               questions: List[Dict]) -> int:
    """
    Create a Round 3 PvP challenge with multiple questions.
    questions: list of {question_id, params, options, correct_index, difficulty}
    Returns challenge_id.
    """
    expires_at = datetime.utcnow().replace(
        hour=16, minute=0, second=0, microsecond=0)
    if datetime.utcnow() >= expires_at:
        expires_at += timedelta(days=1)

    challenger = await get_student_by_id(pool, challenger_id)
    defender   = await get_student_by_id(pool, defender_id)
    tier_gap   = (challenger['tier'] - defender['tier']) if challenger and defender else 0
    is_cross   = (challenger['class_id'] != defender['class_id']) if challenger and defender else False

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO challenge_queue
                   (sender_id, receiver_id, question_id, params, options,
                    correct_index, question_difficulty, sender_tier, receiver_tier,
                    tier_gap, is_cross_class, source, expires_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'r3_forward',$12)
                   RETURNING id""",
                challenger_id, defender_id,
                questions[0]['question_id'],
                json.dumps(questions[0]['params']),
                json.dumps(questions[0]['options']),
                questions[0]['correct_index'],
                questions[0].get('difficulty', 5),
                challenger['tier'] if challenger else 1,
                defender['tier']   if defender   else 1,
                tier_gap, is_cross, expires_at)
            challenge_id = row['id']

            # Track send/receive counts
            await conn.execute(
                "UPDATE students SET r3_sends_tonight = r3_sends_tonight + 1 WHERE id = $1",
                challenger_id)
            await conn.execute(
                "UPDATE students SET r3_received_tonight = r3_received_tonight + 1 WHERE id = $1",
                defender_id)

            return challenge_id


async def get_r3_challenge(pool: asyncpg.Pool, challenge_id: int) -> Optional[Dict]:
    """Get a challenge_queue row — includes challenger_id/defender_id aliases."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT *,
                      sender_id   AS challenger_id,
                      receiver_id AS defender_id
               FROM challenge_queue WHERE id = $1""",
            challenge_id)
        return _row(row)


async def get_r3_challenge_question(pool: asyncpg.Pool,
                                    challenge_id: int,
                                    q_index: int = 0) -> Optional[Dict]:
    """
    Get question data for a challenge at a given q_index.
    For MVP single-question challenges, q_index is always 0 — returns
    the question embedded in challenge_queue itself.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT cq.id AS challenge_id,
                      cq.question_id, cq.params, cq.options, cq.correct_index,
                      cq.question_difficulty AS difficulty,
                      q.question_template, q.answer_formula
               FROM challenge_queue cq
               JOIN questions q ON cq.question_id = q.id
               WHERE cq.id = $1""",
            challenge_id)
        return _row(row)


async def set_r3_current_message(pool: asyncpg.Pool,
                                  challenge_id: int,
                                  message_id: int,
                                  role: str = 'defender') -> None:
    """Store the DM message_id for a challenge party (defender or challenger)."""
    col = 'defender_message_id' if role == 'defender' else 'challenger_message_id'
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE challenge_queue SET {col} = $2 WHERE id = $1",
            challenge_id, message_id)


async def accept_r3_challenge(pool: asyncpg.Pool, challenge_id: int) -> None:
    """Mark a challenge as accepted (defender agreed to play)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE challenge_queue SET status = 'accepted' WHERE id = $1",
            challenge_id)


async def decline_r3_challenge(pool: asyncpg.Pool, challenge_id: int) -> None:
    """Mark a challenge as declined."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE challenge_queue SET status = 'declined' WHERE id = $1",
            challenge_id)


async def record_r3_answer(pool: asyncpg.Pool,
                            challenge_id: int,
                            student_id: int,
                            answer_index: int,
                            is_correct: bool) -> tuple:
    """
    Record a defender's answer on a R3 challenge.
    Returns (new_q_index, correct_count) — for MVP always (1, int).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO challenge_responses
                   (challenge_id, student_id, answer_index, is_correct)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (challenge_id, student_id) DO UPDATE
                     SET answer_index = $3, is_correct = $4, answered_at = NOW()""",
                challenge_id, student_id, answer_index, is_correct)
            new_q_index   = 1  # MVP: single question
            correct_count = 1 if is_correct else 0
            return new_q_index, correct_count


async def close_r3_challenge(pool: asyncpg.Pool,
                              challenge_id: int,
                              defender_xp: int = 0,
                              challenger_xp: int = 0) -> None:
    """Mark challenge answered and record final XP."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE challenge_queue SET status = 'answered' WHERE id = $1",
            challenge_id)


async def get_stale_r3_challenges(pool: asyncpg.Pool) -> List[Dict]:
    """Pending challenges past their expiry — for timeout sweep."""
    async with pool.acquire() as conn:
        return _rows(await conn.fetch(
            """SELECT * FROM challenge_queue
               WHERE status IN ('pending', 'accepted')
               AND expires_at <= NOW()"""))


async def get_r3_sent_count_today(pool: asyncpg.Pool, student_id: int) -> int:
    """Count R3 challenges sent by student today."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT COUNT(*) AS cnt FROM challenge_queue
               WHERE sender_id = $1 AND session_date = CURRENT_DATE
               AND source = 'r3_forward'""",
            student_id)
        return int(row['cnt']) if row else 0


async def increment_r3_sent_count(pool: asyncpg.Pool, student_id: int) -> None:
    """Bump r3_sends_tonight counter."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET r3_sends_tonight = r3_sends_tonight + 1 WHERE id = $1",
            student_id)


# =============================================================================
# SHOP — MISSING FUNCTIONS
# =============================================================================

async def get_student_inventory(pool: asyncpg.Pool, student_id: int) -> List[Dict]:
    """Alias for get_inventory."""
    return await get_inventory(pool, student_id)


async def activate_item_flag(pool: asyncpg.Pool,
                              student_id: int,
                              flag: str) -> None:
    """
    Generic boolean flag setter on students table.
    flag must be one of the known item flag columns.
    """
    allowed = {
        'shield_active', 'extension_active', 'double_down_active',
        'trap_active', 'spy_used_today'
    }
    if flag not in allowed:
        raise ValueError(f"Unknown item flag: {flag}")
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE students SET {flag} = TRUE WHERE id = $1",
            student_id)


async def consume_inventory_item(pool: asyncpg.Pool,
                                  student_id: int,
                                  item_key: str) -> bool:
    """Alias for consume_item."""
    return await consume_item(pool, student_id, item_key)


async def _purchase_item_full(pool: asyncpg.Pool,
                               student_id: int,
                               item_key: str) -> Dict:
    """Internal full-result purchase — returns {'ok', 'reason', 'new_coins'}.
    The public purchase_item (defined earlier) calls this."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            item = await conn.fetchrow(
                "SELECT * FROM shop_items WHERE effect_key = $1 AND is_active = TRUE",
                item_key)
            if not item:
                return {'ok': False, 'reason': 'item_not_found', 'new_coins': 0}
            student = await conn.fetchrow(
                "SELECT coins FROM students WHERE id = $1", student_id)
            if not student or student['coins'] < item['price']:
                return {'ok': False, 'reason': 'insufficient_coins',
                        'new_coins': student['coins'] if student else 0}
            held = await conn.fetchval(
                """SELECT COALESCE(quantity, 0) FROM inventory
                   WHERE student_id = $1 AND item_id = $2""",
                student_id, item['id']) or 0
            if held >= item['max_hold']:
                return {'ok': False, 'reason': 'max_hold_reached', 'new_coins': student['coins']}
            new_coins_row = await conn.fetchrow(
                "UPDATE students SET coins = coins - $2 WHERE id = $1 RETURNING coins",
                student_id, item['price'])
            await conn.execute(
                """INSERT INTO inventory (student_id, item_id, quantity)
                   VALUES ($1, $2, 1)
                   ON CONFLICT (student_id, item_id)
                   DO UPDATE SET quantity = inventory.quantity + 1""",
                student_id, item['id'])
            return {'ok': True, 'reason': 'success',
                    'new_coins': new_coins_row['coins']}


# =============================================================================
# DAILY — MISSING FUNCTIONS
# =============================================================================

async def log_daily_sent(pool: asyncpg.Pool,
                          student_id: int,
                          question_id: int,
                          session_date: Optional[date] = None) -> int:
    """
    Log that a daily question was sent to a student.
    Returns the log id.
    Uses round2_sessions as the daily log table (one per student per night).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO round2_sessions
               (student_id, status, started_at, difficulty_base, final_difficulty)
               VALUES ($1, 'active', NOW(), 5, 5)
               ON CONFLICT (student_id, session_date) DO UPDATE
                 SET status = 'active'
               RETURNING id""",
            student_id)
        return row['id']


async def get_todays_daily_log(pool: asyncpg.Pool, student_id: int) -> Optional[Dict]:
    """Get today's daily session log for a student."""
    return await get_todays_round2_session(pool, student_id)


async def increment_daily_attempts(pool: asyncpg.Pool, student_id: int) -> None:
    """Bump the attempt counter on the student's daily log."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_sessions
               SET correct_count = correct_count  -- placeholder: attempts tracked via questions
               WHERE student_id = $1 AND session_date = CURRENT_DATE""",
            student_id)


async def update_daily_log_answer(pool: asyncpg.Pool,
                                   log_id: int,
                                   is_correct: bool,
                                   attempts: int) -> None:
    """Record the final answer result on the daily log."""
    status = 'completed' if is_correct else 'expired'
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE round2_sessions
               SET status = $2, completed_at = NOW(),
                   correct_count = $3
               WHERE id = $1""",
            log_id, status, 1 if is_correct else 0)


# =============================================================================
# BADGES — MISSING FUNCTIONS
# =============================================================================

async def award_badge_if_missing(pool: asyncpg.Pool,
                                  student_id: int,
                                  badge_key: str) -> bool:
    """Idempotent badge award — returns True if newly awarded."""
    return await award_badge(pool, student_id, badge_key)


async def check_first_blood_today(pool: asyncpg.Pool,
                                   student_id: int,
                                   today: date) -> bool:
    """True if this student was the first to answer correctly in R1 tonight."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT EXISTS(
                 SELECT 1 FROM battle_group_members bgm
                 JOIN battle_groups bg ON bgm.group_id = bg.id
                 JOIN battle_sessions bs ON bg.session_id = bs.id
                 WHERE bgm.student_id = $1
                 AND bgm.finish_position = 1
                 AND bs.session_date = $2
               ) AS first_blood""",
            student_id, today)
        return bool(row['first_blood']) if row else False


async def check_r2_perfect_today(pool: asyncpg.Pool,
                                  student_id: int,
                                  today: date) -> bool:
    """True if student got 100% accuracy in R2 today."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT correct_count, total_questions
               FROM round2_sessions
               WHERE student_id = $1 AND session_date = $2
               AND status = 'completed'""",
            student_id, today)
        if not row:
            return False
        total = row['total_questions'] or 5
        return row['correct_count'] == total


async def check_social_butterfly(pool: asyncpg.Pool, student_id: int) -> bool:
    """True if student has sent+received >= 5 R3 challenges total."""
    async with pool.acquire() as conn:
        sent = await conn.fetchval(
            "SELECT COUNT(*) FROM challenge_queue WHERE sender_id = $1", student_id) or 0
        received = await conn.fetchval(
            "SELECT COUNT(*) FROM challenge_responses WHERE student_id = $1", student_id) or 0
        return (sent + received) >= 5


# =============================================================================
# ADMIN — MISSING FUNCTIONS
# =============================================================================

async def get_daily_stats(pool: asyncpg.Pool) -> Dict:
    """Today's participation stats for admin dashboard."""
    async with pool.acquire() as conn:
        total_active = await conn.fetchval(
            "SELECT COUNT(*) FROM students WHERE is_active = TRUE") or 0
        r1_participants = await conn.fetchval(
            """SELECT COUNT(DISTINCT bgm.student_id)
               FROM battle_group_members bgm
               JOIN battle_groups bg ON bgm.group_id = bg.id
               JOIN battle_sessions bs ON bg.session_id = bs.id
               WHERE bs.session_date = CURRENT_DATE""") or 0
        r2_completed = await conn.fetchval(
            """SELECT COUNT(*) FROM round2_sessions
               WHERE session_date = CURRENT_DATE AND status = 'completed'""") or 0
        r3_answered = await conn.fetchval(
            """SELECT COUNT(*) FROM challenge_queue
               WHERE session_date = CURRENT_DATE AND status = 'answered'""") or 0
        pending_approvals = await conn.fetchval(
            "SELECT COUNT(*) FROM students WHERE is_active = FALSE") or 0
        return {
            'total_active':     total_active,
            'r1_participants':  r1_participants,
            'r2_completed':     r2_completed,
            'r3_answered':      r3_answered,
            'pending_approvals': pending_approvals,
        }


async def create_boss_battle(pool: asyncpg.Pool,
                              title_zh: str,
                              grade: str,
                              question_id: int,
                              params: Dict,
                              options: List,
                              correct_index: int,
                              max_hp: int,
                              xp_reward: int,
                              coins_reward: int,
                              scope: str = 'grade',
                              class_id: Optional[int] = None,
                              created_by: Optional[int] = None,
                              duration_minutes: int = 30) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO boss_raids
               (title_zh, grade, scope, class_id, question_id, params, options,
                correct_index, max_hp, current_hp, xp_reward, coins_reward,
                starts_at, expires_at, is_active, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$9,$10,$11,
                       NOW(), NOW() + ($12 * INTERVAL '1 minute'), TRUE, $13)
               RETURNING id""",
            title_zh, grade, scope, class_id, question_id,
            json.dumps(params), json.dumps(options), correct_index,
            max_hp, xp_reward, coins_reward, duration_minutes, created_by)
        return row['id']


# =============================================================================
# NIGHTLY / TOURNAMENT — MISSING FUNCTIONS
# =============================================================================

async def resolve_class_tournament(pool: asyncpg.Pool, grade: str) -> List[Dict]:
    """Alias for resolve_weekly_tournaments for the current week."""
    from datetime import timedelta
    today = date.today()
    # Find the Monday of current week
    week_start = today - timedelta(days=today.weekday())
    return await resolve_weekly_tournaments(pool, grade, week_start)


async def award_tournament_prize_to_class(pool: asyncpg.Pool,
                                           class_id: int,
                                           coins: int,
                                           reason: str = 'tournament') -> None:
    """Award coins to all active members of a class."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE students SET coins = coins + $2
               WHERE class_id = $1 AND is_active = TRUE""",
            class_id, coins)


async def create_weekly_tournament(pool: asyncpg.Pool,
                                    grade: str,
                                    week_start: date,
                                    week_end: date) -> int:
    """Create a single grade-wide tournament record, return its id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tournaments (grade, scope, week_start, week_end)
               VALUES ($1, 'grade', $2, $3)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            grade, week_start, week_end)
        return row['id'] if row else 0


# =============================================================================
# CHALLENGE.PY LEGACY — old challenge_questions table functions
# These support the older challenge.py handler that uses a separate
# challenge_questions join table rather than the inline R3 model.
# =============================================================================

async def get_challenge_questions(pool: asyncpg.Pool,
                                   challenge_id: int) -> List[Dict]:
    """Get all questions for a challenge (legacy challenge.py handler)."""
    async with pool.acquire() as conn:
        # Fallback: return the single question embedded in challenge_queue
        row = await conn.fetchrow(
            """SELECT cq.id AS cq_id, cq.question_id,
                      cq.params, cq.options, cq.correct_index,
                      q.question_template, q.answer_formula, q.difficulty
               FROM challenge_queue cq
               JOIN questions q ON cq.question_id = q.id
               WHERE cq.id = $1""",
            challenge_id)
        return [_row(row)] if row else []


async def add_challenge_question(pool: asyncpg.Pool,
                                  challenge_id: int,
                                  question_id: int,
                                  params: Dict,
                                  options: List,
                                  correct_index: int) -> int:
    """
    Legacy: add a question to a challenge.
    In the current schema this is a no-op (question is stored on challenge_queue).
    Returns 0 as placeholder id.
    """
    return 0


async def update_challenge_question_answer(pool: asyncpg.Pool,
                                            cq_id: int,
                                            is_correct: bool) -> None:
    """
    Legacy: record answer on a challenge question row.
    In current schema, delegates to updating challenge_responses.
    cq_id here is treated as challenge_id.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE challenge_queue
               SET status = 'answered'
               WHERE id = $1""",
            cq_id)
