"""
handlers/round3.py — MathBot MVP v2.0
Round 3: Peer Challenges (sent from R2, answered anytime before midnight)

Flow:
  1. Challenger picks a target during R2 completion prompt
     → round2.handle_r2_challenge_target() creates the challenge record
     → calls round3.notify_challenge_received() to DM the target

  2. Target receives DM with challenge info + "Accept" button
     → handle_r3_accept() sends first of 3 questions

  3. Target answers each question via inline buttons
     → handle_r3_answer() records answer, sends next question or resolves

  4. [Midnight] midnight_reset() calls expire_r3_challenges()
     → marks all pending/accepted challenges as expired
     → challenger gets timeout-win XP, defender gets nothing

Public API (called from round2):
    notify_challenge_received(bot, pool, challenge_id, challenger, target)

Public API (main.py handlers):
    handle_r3_accept        — CallbackQueryHandler ^r3_accept_
    handle_r3_answer        — CallbackQueryHandler ^r3_ans_
    handle_r3_decline       — CallbackQueryHandler ^r3_decline_

Public API (nightly.py):
    expire_r3_challenges(bot, pool)
"""
import logging
from typing import List, Dict, Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db
from utils import messages as msg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XP / Coin rewards
# ---------------------------------------------------------------------------

# Defender answers all 3 correctly → wins the challenge
R3_DEFENDER_WIN_XP = 60
R3_DEFENDER_WIN_COINS = 12
# Challenger wins (defender answered wrong or timed out)
R3_CHALLENGER_WIN_XP = 50
R3_CHALLENGER_WIN_COINS = 10
# Consolation for losing side
R3_CONSOLATION_XP = 10
# Timeout: challenger gets half win reward
R3_TIMEOUT_WIN_XP = 25
R3_TIMEOUT_WIN_COINS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r3_answer_keyboard(challenge_id: int, q_index: int, options: List[str]) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D"]
    rows = []
    for i, opt in enumerate(options):
        cb = f"{config.CB_R3_ANSWER}{challenge_id}_{q_index}_{i}"
        rows.append([InlineKeyboardButton(f"{labels[i]}. {opt}", callback_data=cb)])
    return InlineKeyboardMarkup(rows)


def _accept_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 接受挑戰", callback_data=f"{config.CB_R3_ACCEPT}{challenge_id}"),
        InlineKeyboardButton("❌ 拒絕", callback_data=f"{config.CB_R3_DECLINE}{challenge_id}"),
    ]])


async def _send_r3_question(
    bot,
    pool,
    challenge_id: int,
    q_index: int,
    defender: Dict[str, Any],
) -> None:
    """Send question q_index of the R3 challenge to the defender."""
    cq = await db.get_r3_challenge_question(pool, challenge_id=challenge_id, q_index=q_index)
    if not cq:
        logger.error("R3: no question at index %d for challenge %d", q_index, challenge_id)
        return

    options: List[str] = cq["options"]
    question_text: str = cq["question_text"]
    difficulty: int = cq.get("difficulty", 1)
    diff_stars = "⭐" * difficulty

    keyboard = _r3_answer_keyboard(challenge_id, q_index, options)
    text = (
        f"⚔️ *挑戰題目 {q_index + 1}/3*  {diff_stars}\n\n"
        f"{question_text}"
    )

    try:
        sent = await bot.send_message(
            chat_id=defender["telegram_id"],
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await db.set_r3_current_message(
            pool, challenge_id=challenge_id, message_id=sent.message_id
        )
    except TelegramError as e:
        logger.error("R3: failed to send question to defender %s: %s", defender["id"], e)


async def _resolve_challenge(
    bot,
    pool,
    challenge_id: int,
    defender_won: bool,
    timed_out: bool = False,
) -> None:
    """
    Award XP/coins to both sides, close the challenge record,
    and send result DMs to both challenger and defender.
    """
    challenge = await db.get_r3_challenge(pool, challenge_id)
    if not challenge or challenge["status"] not in ("accepted", "pending"):
        return

    challenger = await db.get_student_by_id(pool, challenge["challenger_id"])
    defender = await db.get_student_by_id(pool, challenge["defender_id"])
    if not challenger or not defender:
        return

    if timed_out:
        c_xp, c_coins = R3_TIMEOUT_WIN_XP, R3_TIMEOUT_WIN_COINS
        d_xp, d_coins = 0, 0
        winner_label = "timeout"
        c_result = f"⏰ *對手未在時限內回應——你贏了！*\n\n🎖 +{c_xp} XP　🪙 +{c_coins} 硬幣"
        d_result = f"⏰ *挑戰已過期。*\n\n你未能在時限內完成挑戰。"
    elif defender_won:
        c_xp, c_coins = R3_CONSOLATION_XP, 0
        d_xp, d_coins = R3_DEFENDER_WIN_XP, R3_DEFENDER_WIN_COINS
        winner_label = "defender"
        c_result = (
            f"😤 *{defender['display_name']} 成功防守！*\n\n"
            f"🎖 +{c_xp} XP（參與獎）"
        )
        d_result = (
            f"🏆 *你成功防守了 {challenger['display_name']} 的挑戰！*\n\n"
            f"🎖 +{d_xp} XP　🪙 +{d_coins} 硬幣"
        )
    else:
        c_xp, c_coins = R3_CHALLENGER_WIN_XP, R3_CHALLENGER_WIN_COINS
        d_xp, d_coins = R3_CONSOLATION_XP, 0
        winner_label = "challenger"
        c_result = (
            f"🏆 *你的挑戰成功！{defender['display_name']} 答錯了！*\n\n"
            f"🎖 +{c_xp} XP　🪙 +{c_coins} 硬幣"
        )
        d_result = (
            f"😤 *{challenger['display_name']} 的挑戰勝出。*\n\n"
            f"🎖 +{d_xp} XP（參與獎）"
        )

    # Apply rewards
    await db.apply_xp_and_coins(pool, student_id=challenge["challenger_id"], xp=c_xp, coins=c_coins)
    await db.apply_xp_and_coins(pool, student_id=challenge["defender_id"], xp=d_xp, coins=d_coins)

    # Close challenge
    await db.close_r3_challenge(
        pool,
        challenge_id=challenge_id,
        winner=winner_label,
        challenger_xp=c_xp,
        challenger_coins=c_coins,
        defender_xp=d_xp,
        defender_coins=d_coins,
    )

    # Notify both
    for student, text in [(challenger, c_result), (defender, d_result)]:
        try:
            await bot.send_message(
                chat_id=student["telegram_id"],
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.error("R3: failed to send result to student %s: %s", student["id"], e)


# ---------------------------------------------------------------------------
# Called from round2 — notify target of incoming challenge
# ---------------------------------------------------------------------------

async def notify_challenge_received(
    bot,
    pool,
    challenge_id: int,
    challenger: Dict[str, Any],
    target: Dict[str, Any],
) -> None:
    """DM the defender about the incoming challenge with accept/decline buttons."""
    keyboard = _accept_keyboard(challenge_id)
    text = (
        f"⚔️ *{challenger['display_name']} 向你發起挑戰！*\n\n"
        f"3 道數學題，全部答對你就贏！\n"
        f"今晚午夜前有效。\n\n"
        f"🎖 贏：+{R3_DEFENDER_WIN_XP} XP / +{R3_DEFENDER_WIN_COINS} 硬幣"
    )
    try:
        await bot.send_message(
            chat_id=target["telegram_id"],
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except TelegramError as e:
        logger.error("R3: failed to notify defender %s: %s", target["id"], e)


# ---------------------------------------------------------------------------
# handle_r3_accept  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r3_accept(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Defender accepts the challenge — send first question."""
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    telegram_id = update.effective_user.id

    try:
        challenge_id = int(query.data.replace(config.CB_R3_ACCEPT, "", 1))
    except ValueError:
        await query.edit_message_text("❌ 無效操作。")
        return

    defender = await db.get_student_by_telegram_id(pool, telegram_id)
    if not defender:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    challenge = await db.get_r3_challenge(pool, challenge_id)
    if not challenge:
        await query.edit_message_text("❌ 找不到挑戰記錄。")
        return

    if challenge["defender_id"] != defender["id"]:
        await query.answer("❌ 這不是你的挑戰！", show_alert=True)
        return

    if challenge["status"] != "pending":
        await query.edit_message_text("❌ 這個挑戰已過期或已作答。")
        return

    # Mark as accepted
    await db.accept_r3_challenge(pool, challenge_id)
    await query.edit_message_text(
        f"✅ 已接受挑戰！第一題來了……", parse_mode="Markdown"
    )

    await _send_r3_question(context.bot, pool, challenge_id, q_index=0, defender=defender)


# ---------------------------------------------------------------------------
# handle_r3_decline  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r3_decline(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Defender declines the challenge."""
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    telegram_id = update.effective_user.id

    try:
        challenge_id = int(query.data.replace(config.CB_R3_DECLINE, "", 1))
    except ValueError:
        await query.edit_message_text("❌ 無效操作。")
        return

    defender = await db.get_student_by_telegram_id(pool, telegram_id)
    if not defender:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    challenge = await db.get_r3_challenge(pool, challenge_id)
    if not challenge or challenge["defender_id"] != defender["id"]:
        await query.edit_message_text("❌ 找不到挑戰記錄。")
        return

    if challenge["status"] != "pending":
        await query.edit_message_text("這個挑戰已過期。")
        return

    await db.decline_r3_challenge(pool, challenge_id)
    await query.edit_message_text("👍 已拒絕挑戰。")

    # Notify challenger
    challenger = await db.get_student_by_id(pool, challenge["challenger_id"])
    if challenger:
        try:
            await context.bot.send_message(
                chat_id=challenger["telegram_id"],
                text=f"😶 *{defender['display_name']}* 拒絕了你的挑戰。",
                parse_mode="Markdown",
            )
        except TelegramError:
            pass


# ---------------------------------------------------------------------------
# handle_r3_answer  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r3_answer(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Defender answers a challenge question.
    Callback data: CB_R3_ANSWER + "{challenge_id}_{q_index}_{option_idx}"
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
        raw = query.data.replace(config.CB_R3_ANSWER, "", 1)
        parts = raw.split("_")
        challenge_id = int(parts[0])
        q_index = int(parts[1])
        selected_idx = int(parts[2])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ 無效回應，請重試。")
        return

    defender = await db.get_student_by_telegram_id(pool, telegram_id)
    if not defender:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    challenge = await db.get_r3_challenge(pool, challenge_id)
    if not challenge or challenge["defender_id"] != defender["id"]:
        await query.edit_message_text("❌ 找不到挑戰記錄。")
        return

    if challenge["status"] != "accepted":
        await query.edit_message_text("⏰ 挑戰已結束。")
        return

    # Verify it's the expected question
    if challenge.get("current_q_index", 0) != q_index:
        await query.answer("你已經作答了！", show_alert=True)
        return

    cq = await db.get_r3_challenge_question(pool, challenge_id=challenge_id, q_index=q_index)
    if not cq:
        await query.edit_message_text("❌ 找不到題目。")
        return

    correct_idx: int = cq["correct_option_index"]
    options: List[str] = cq["options"]
    is_correct = (selected_idx == correct_idx)

    correct_label = ["A", "B", "C", "D"][correct_idx]
    correct_text = f"{correct_label}. {options[correct_idx]}"

    if is_correct:
        feedback = f"✅ *答對！*\n正確答案：{correct_text}"
    else:
        feedback = f"❌ *答錯！*\n正確答案：{correct_text}"

    try:
        await query.edit_message_text(feedback, parse_mode="Markdown")
    except TelegramError:
        pass

    # Record answer and advance
    new_q_index, correct_count = await db.record_r3_answer(
        pool,
        challenge_id=challenge_id,
        q_index=q_index,
        is_correct=is_correct,
    )

    if new_q_index < 3:
        # Send next question
        await _send_r3_question(context.bot, pool, challenge_id, q_index=new_q_index, defender=defender)
    else:
        # All 3 answered — defender wins only if all 3 correct
        defender_won = (correct_count == 3)
        await _resolve_challenge(context.bot, pool, challenge_id, defender_won=defender_won)


# ---------------------------------------------------------------------------
# Nightly — expire_r3_challenges  (called from nightly.midnight_reset)
# ---------------------------------------------------------------------------

async def expire_r3_challenges(
    bot,
    pool,
) -> None:
    """
    Called at midnight. Find all still-pending/accepted R3 challenges,
    mark them expired, and award timeout XP to challengers.
    """
    try:
        stale = await db.get_stale_r3_challenges(pool)
        logger.info("R3 expire: %d stale challenges", len(stale))

        for challenge in stale:
            await _resolve_challenge(
                bot, pool, challenge["id"], defender_won=False, timed_out=True
            )

        logger.info("R3 expire: complete")

    except Exception as e:
        logger.exception("R3 expire: crashed: %s", e)
