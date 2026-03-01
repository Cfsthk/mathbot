"""
handlers/round2.py — MathBot MVP v2.0
Round 2: Solo Accuracy Session (8:15 PM HKT, after R1 closes)

Flow:
  1. [8:15pm] open_r2_sessions() is called by scheduler
     - Finds all active students who completed R1
     - Creates an r2_session row (status=open, q_index=0, correct_count=0)
     - Sends first question DM to each student

  2. [Student taps answer button]
     - handle_r2_answer() records answer
     - Difficulty adjusts based on correctness (adaptive):
         correct  → difficulty +1 (max 5)
         wrong    → difficulty -1 (min 1)
     - If q_index < 4: send next question
     - If q_index == 4 (5th question done): close session, compute rewards, send summary
     - Show "Challenge a classmate?" prompt after final question

  3. [Student taps "Challenge"] → handle_r2_send_challenge()
     - Lists active classmates as inline targets
     - Student picks a target → creates r3_challenge row → sends notification to target

  4. [10:00pm] close_r2_sessions() hard-closes any still-open sessions
     - Awards partial XP for questions already answered
     - Sends timeout DM

Public API (scheduler):
    open_r2_sessions(context)   — 8:15pm
    close_r2_sessions(context)  — 10:00pm

Public API (main.py handlers):
    handle_r2_answer            — CallbackQueryHandler ^r2_ans_
    handle_r2_challenge_target  — CallbackQueryHandler ^r2_chal_
"""
import logging
import random
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db
from game import questions as q_module
from utils import messages as msg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

R2_QUESTION_COUNT = 5

# XP per correct answer by difficulty tier (1-5)
R2_XP_PER_CORRECT = {1: 10, 2: 14, 3: 18, 4: 24, 5: 30}
# Bonus XP for completing all 5 with N correct
R2_COMPLETION_BONUS = {5: 30, 4: 15, 3: 5, 2: 0, 1: 0, 0: 0}
# Coin reward for perfect 5/5
R2_PERFECT_COINS = 10
# Participation XP for partial/timeout (per answered question)
R2_PARTICIPATION_XP = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r2_keyboard(session_id: int, options: List[str]) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D"]
    rows = []
    for i, opt in enumerate(options):
        cb = f"{config.CB_R2_ANSWER}{session_id}_{i}"
        rows.append([InlineKeyboardButton(f"{labels[i]}. {opt}", callback_data=cb)])
    return InlineKeyboardMarkup(rows)


def _challenge_keyboard(session_id: int, targets: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for t in targets[:8]:  # cap at 8 buttons
        cb = f"{config.CB_R2_CHALLENGE}{session_id}_{t['id']}"
        rows.append([InlineKeyboardButton(t["display_name"], callback_data=cb)])
    rows.append([InlineKeyboardButton("⏭ 跳過", callback_data=f"{config.CB_R2_CHALLENGE}{session_id}_skip")])
    return InlineKeyboardMarkup(rows)


def _difficulty_label(diff: int) -> str:
    return {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}.get(diff, "⭐")


async def _send_next_question(
    bot,
    pool,
    session: Dict[str, Any],
    student: Dict[str, Any],
) -> None:
    """Fetch and send the next question for this R2 session."""
    session_id: int = session["id"]
    q_index: int = session["q_index"]
    difficulty: int = session["current_difficulty"]
    grade: str = student["grade"]

    question = await db.get_random_question(
        pool, grade=grade, diff_min=difficulty, diff_max=difficulty
    )
    if not question:
        # Fallback: any difficulty for this grade
        question = await db.get_random_question(pool, grade=grade, diff_min=1, diff_max=5)
    if not question:
        logger.error("R2: no question available for grade=%s diff=%d", grade, difficulty)
        return

    question_text = q_module.render_question_text(question)
    options: List[str] = question["options"]
    correct_idx: int = question["correct_option_index"]

    # Persist question assignment
    await db.set_r2_session_question(
        pool,
        session_id=session_id,
        q_index=q_index,
        question_id=question["id"],
        options=options,
        correct_option_index=correct_idx,
    )

    keyboard = _r2_keyboard(session_id, options)
    text = (
        f"📝 *第二輪 — 題目 {q_index + 1}/{R2_QUESTION_COUNT}*\n"
        f"難度：{_difficulty_label(difficulty)}\n\n"
        f"{question_text}"
    )

    try:
        sent = await bot.send_message(
            chat_id=student["telegram_id"],
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await db.set_r2_session_current_message(pool, session_id=session_id, message_id=sent.message_id)
    except TelegramError as e:
        logger.error("R2: failed to send question to student %s: %s", student["id"], e)


async def _close_session_and_reward(
    bot,
    pool,
    session: Dict[str, Any],
    student: Dict[str, Any],
    timed_out: bool = False,
) -> None:
    """
    Compute final rewards for a completed/timed-out session,
    apply to DB, send summary DM, then offer challenge prompt.
    """
    session_id: int = session["id"]
    correct_count: int = session.get("correct_count", 0)
    answered_count: int = session.get("answered_count", 0)

    if timed_out:
        xp_earned = answered_count * R2_PARTICIPATION_XP
        coins_earned = 0
        summary_header = "⏰ *第二輪結束（時間到）*"
    else:
        xp_earned = session.get("xp_accumulated", 0)
        xp_earned += R2_COMPLETION_BONUS.get(correct_count, 0)
        coins_earned = R2_PERFECT_COINS if correct_count == R2_QUESTION_COUNT else 0
        summary_header = "✅ *第二輪完成！*"

    new_xp, leveled_up, new_rank = await db.apply_xp_and_coins(
        pool, student_id=student["id"], xp=xp_earned, coins=coins_earned
    )

    await db.close_r2_session(pool, session_id=session_id, xp_earned=xp_earned, coins_earned=coins_earned)

    # Build summary text
    stars = "⭐" * correct_count + "☆" * (R2_QUESTION_COUNT - correct_count)
    summary = (
        f"{summary_header}\n\n"
        f"答對：{correct_count}/{R2_QUESTION_COUNT}  {stars}\n\n"
        f"🎖 +{xp_earned} XP"
    )
    if coins_earned:
        summary += f"　🪙 +{coins_earned} 硬幣（全對獎勵！）"
    summary += f"\n📊 總 XP：{new_xp}"
    if leveled_up and new_rank:
        summary += f"\n\n🆙 *升級！你現在是 {new_rank['title_zh']}！*"

    try:
        await bot.send_message(
            chat_id=student["telegram_id"],
            text=summary,
            parse_mode="Markdown",
        )
    except TelegramError as e:
        logger.error("R2: failed to send summary to student %s: %s", student["id"], e)
        return

    # Offer challenge prompt (skip if timed out or no classmates available)
    if not timed_out:
        await _offer_challenge_prompt(bot, pool, session_id, student)


async def _offer_challenge_prompt(
    bot,
    pool,
    session_id: int,
    student: Dict[str, Any],
) -> None:
    """Send 'challenge a classmate?' prompt after R2 completion."""
    targets = await db.get_challengeable_classmates(
        pool,
        student_id=student["id"],
        class_id=student["class_id"],
    )
    if not targets:
        return

    keyboard = _challenge_keyboard(session_id, targets)
    try:
        await bot.send_message(
            chat_id=student["telegram_id"],
            text=(
                "⚔️ *挑戰同學！*\n\n"
                "選一位同學，向他們發送 3 題挑戰\\!\n"
                "勝出可得額外 XP 和硬幣💰"
            ),
            reply_markup=keyboard,
            parse_mode="MarkdownV2",
        )
    except TelegramError as e:
        logger.error("R2: failed to send challenge prompt to student %s: %s", student["id"], e)


# ---------------------------------------------------------------------------
# Step 1 — open_r2_sessions  (8:15pm job)
# ---------------------------------------------------------------------------

async def open_r2_sessions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Called by scheduler at 8:15pm HKT.
    Creates an R2 session for every active student and sends their first question.
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("R2: DB pool not available")
        return

    bot = context.bot

    try:
        students = await db.get_active_students(pool)
        logger.info("R2: opening sessions for %d students", len(students))

        for student in students:
            student_id: int = student["id"]
            tier: int = student.get("tier", 1)
            diff_min, diff_max = config.TIER_DIFFICULTY_RANGE.get(tier, (1, 3))
            start_difficulty = (diff_min + diff_max) // 2

            # Create session row
            session_id = await db.create_r2_session(
                pool,
                student_id=student_id,
                start_difficulty=start_difficulty,
            )

            session = {
                "id": session_id,
                "q_index": 0,
                "current_difficulty": start_difficulty,
                "correct_count": 0,
                "answered_count": 0,
                "xp_accumulated": 0,
            }

            await _send_next_question(bot, pool, session, student)

        logger.info("R2: open_r2_sessions complete")

    except Exception as e:
        logger.exception("R2: open_r2_sessions crashed: %s", e)


# ---------------------------------------------------------------------------
# Step 2 — handle_r2_answer  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r2_answer(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Student taps MCQ button in R2 DM.
    Callback data: CB_R2_ANSWER + "{session_id}_{option_index}"
    e.g.  "r2_ans_17_2"
    """
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    telegram_id = update.effective_user.id

    # Parse callback
    try:
        raw = query.data.replace(config.CB_R2_ANSWER, "", 1)
        session_id_str, opt_str = raw.rsplit("_", 1)
        session_id = int(session_id_str)
        selected_idx = int(opt_str)
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ 無效回應，請重試。")
        return

    student = await db.get_student_by_telegram_id(pool, telegram_id)
    if not student or student["status"] != "active":
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    session = await db.get_r2_session(pool, session_id)
    if not session:
        await query.edit_message_text("❌ 找不到答題記錄。")
        return

    if session["student_id"] != student["id"]:
        await query.answer("❌ 不是你的題目！", show_alert=True)
        return

    if session["status"] != "open":
        await query.edit_message_text("⏰ 這輪已結束。")
        return

    if session["q_index"] != session.get("current_q_index", session["q_index"]):
        await query.answer("你已經作答了！", show_alert=True)
        return

    # Check answer
    correct_idx: int = session["correct_option_index"]
    options: List[str] = session["current_options"]
    is_correct = (selected_idx == correct_idx)

    correct_label = ["A", "B", "C", "D"][correct_idx]
    correct_text = f"{correct_label}. {options[correct_idx]}"
    selected_label = ["A", "B", "C", "D"][selected_idx]

    # Compute XP for this question
    difficulty: int = session["current_difficulty"]
    q_xp = R2_XP_PER_CORRECT.get(difficulty, 10) if is_correct else 0

    # Adaptive difficulty for next question
    if is_correct:
        next_difficulty = min(difficulty + 1, 5)
        feedback = f"✅ *答對！* ({selected_label})\n正確答案：{correct_text}\n🎖 +{q_xp} XP"
    else:
        next_difficulty = max(difficulty - 1, 1)
        feedback = f"❌ *答錯！*\n正確答案：{correct_text}"

    # Update session in DB
    new_q_index, new_correct_count, new_xp_acc = await db.advance_r2_session(
        pool,
        session_id=session_id,
        is_correct=is_correct,
        xp_earned=q_xp,
        next_difficulty=next_difficulty,
    )

    # Edit current message to show feedback (remove buttons)
    try:
        await query.edit_message_text(feedback, parse_mode="Markdown")
    except TelegramError:
        pass

    # Reload session state for next step
    updated_session = {
        "id": session_id,
        "q_index": new_q_index,
        "current_difficulty": next_difficulty,
        "correct_count": new_correct_count,
        "answered_count": session.get("answered_count", 0) + 1,
        "xp_accumulated": new_xp_acc,
    }

    if new_q_index < R2_QUESTION_COUNT:
        # Send next question
        await _send_next_question(context.bot, pool, updated_session, student)
    else:
        # Session complete — compute final rewards
        await _close_session_and_reward(context.bot, pool, updated_session, student, timed_out=False)


# ---------------------------------------------------------------------------
# Step 3 — handle_r2_challenge_target  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r2_challenge_target(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Student picks a challenge target after R2 completion.
    Callback data: CB_R2_CHALLENGE + "{session_id}_{target_student_id|skip}"
    e.g.  "r2_chal_17_42"  or  "r2_chal_17_skip"
    """
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    telegram_id = update.effective_user.id

    # Parse callback
    try:
        raw = query.data.replace(config.CB_R2_CHALLENGE, "", 1)
        session_id_str, target_str = raw.rsplit("_", 1)
        session_id = int(session_id_str)
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ 無效操作。")
        return

    if target_str == "skip":
        await query.edit_message_text("👍 好的，下次再挑戰！")
        return

    try:
        target_id = int(target_str)
    except ValueError:
        await query.edit_message_text("❌ 無效目標。")
        return

    challenger = await db.get_student_by_telegram_id(pool, telegram_id)
    if not challenger or challenger["status"] != "active":
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    target = await db.get_student_by_id(pool, target_id)
    if not target or target["status"] != "active":
        await query.edit_message_text("❌ 找不到對手，請選其他同學。")
        return

    # Prevent self-challenge
    if target_id == challenger["id"]:
        await query.edit_message_text("❌ 不能挑戰自己！")
        return

    # Check daily R3 send limit
    sent_today = await db.get_r3_sent_count_today(pool, challenger["id"])
    if sent_today >= config.R3_MAX_CHALLENGES_PER_DAY:
        await query.edit_message_text(
            f"❌ 今日挑戰次數已達上限（{config.R3_MAX_CHALLENGES_PER_DAY} 次）。"
        )
        return

    # Pick 3 questions for the challenge (escalating difficulty)
    grade: str = challenger["grade"]
    tier: int = challenger.get("tier", 1)
    diff_min, _ = config.TIER_DIFFICULTY_RANGE.get(tier, (1, 3))

    challenge_questions = []
    for i in range(3):
        diff = min(diff_min + i, 5)
        q = await db.get_random_question(pool, grade=grade, diff_min=diff, diff_max=diff)
        if not q:
            q = await db.get_random_question(pool, grade=grade, diff_min=1, diff_max=5)
        if q:
            challenge_questions.append({
                "question_id": q["id"],
                "options": q["options"],
                "correct_option_index": q["correct_option_index"],
                "question_text": q_module.render_question_text(q),
                "difficulty": diff,
            })

    if len(challenge_questions) < 3:
        await query.edit_message_text("❌ 暫時沒有足夠題目，請稍後再試。")
        return

    # Create R3 challenge record
    challenge_id = await db.create_r3_challenge(
        pool,
        challenger_id=challenger["id"],
        defender_id=target_id,
        questions=challenge_questions,
    )

    await db.increment_r3_sent_count(pool, challenger["id"])

    # Notify challenger (edit the prompt message)
    await query.edit_message_text(
        f"⚔️ 已向 *{target['display_name']}* 發送挑戰！\n\n"
        f"等待對方回應…（今晚午夜前有效）",
        parse_mode="Markdown",
    )

    # Notify target via DM
    from handlers import round3 as r3
    await r3.notify_challenge_received(context.bot, pool, challenge_id, challenger, target)


# ---------------------------------------------------------------------------
# Step 4 — close_r2_sessions  (10:00pm job)
# ---------------------------------------------------------------------------

async def close_r2_sessions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Hard-close all still-open R2 sessions at 10:00pm.
    Award partial participation XP for questions already answered.
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("R2 close: DB pool not available")
        return

    bot = context.bot

    try:
        open_sessions = await db.get_open_r2_sessions(pool)
        logger.info("R2 close: %d open sessions to close", len(open_sessions))

        for session in open_sessions:
            student = await db.get_student_by_id(pool, session["student_id"])
            if not student:
                continue
            await _close_session_and_reward(bot, pool, session, student, timed_out=True)

        logger.info("R2 close: complete")

    except Exception as e:
        logger.exception("R2 close: crashed: %s", e)
