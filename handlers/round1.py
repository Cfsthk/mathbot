"""
handlers/round1.py — MathBot MVP v2.0
Round 1: Nightly Live Battle (8:00 PM HKT)

Flow:
  1. [8:00pm] Scheduler calls open_r1_battles()
     - Queries all active students, groups them by class+tier into groups of 3 (max 5)
     - Creates battle_session, battle_groups, battle_group_members rows
     - Sends a private DM to each member with question + MCQ answer buttons
     - Posts header announcement to each class channel

  2. [Student taps answer button in DM]
     - handle_r1_answer() records answer and finish position (atomic claim)
     - Awards XP + coins based on position (1st=80xp/15c, 2nd=40xp/5c, 3rd=20xp, wrong=10xp)
     - Edits DM to show result
     - If all group members answered, posts result summary to class channel

  3. [8:15pm] Scheduler calls close_r1_battles()
     - Auto-resolves unanswered members (position=0, participation XP)
     - Edits their pending DM to show time-out message
     - Posts final group summary to channel for any unresolved groups

Public API (called from scheduler.py):
    open_r1_battles(context)   — 8:00pm job
    close_r1_battles(context)  — 8:15pm job

Public API (registered in main.py):
    handle_r1_answer           — CallbackQueryHandler pattern ^r1_ans_
"""
import logging
import random
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db
from game import questions as q_module
from utils import messages as msg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r1_keyboard(group_id: int, options: List[str]) -> InlineKeyboardMarkup:
    """Build 4-button MCQ inline keyboard for a Round 1 question."""
    labels = ["A", "B", "C", "D"]
    rows = []
    for i, opt in enumerate(options):
        cb = f"{config.CB_R1_ANSWER}{group_id}_{i}"
        rows.append([InlineKeyboardButton(f"{labels[i]}. {opt}", callback_data=cb)])
    return InlineKeyboardMarkup(rows)


def _position_emoji(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "🏅")


def _format_group_result(members: List[Dict[str, Any]]) -> str:
    """Format a finished group's results for channel announcement."""
    lines = ["📊 *本輪結果*\n"]
    for m in sorted(members, key=lambda x: (x["finish_position"] or 99)):
        pos = m["finish_position"]
        if pos and pos > 0:
            emoji = _position_emoji(pos)
            lines.append(
                f"{emoji} {m['display_name']} — +{m['xp_earned']} XP / +{m['coins_earned']} 硬幣"
            )
        else:
            lines.append(f"⏭ {m['display_name']} — 未作答（+{m['xp_earned']} XP）")
    return "\n".join(lines)


async def _send_result_to_channel(
    bot,
    channel_id: int,
    announcement_msg_id: Optional[int],
    members: List[Dict[str, Any]],
    correct_answer: str,
) -> None:
    """Post round result summary to class channel, threaded under header if possible."""
    if not channel_id:
        return
    result_text = f"✅ *答案：{correct_answer}*\n\n{_format_group_result(members)}"
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=result_text,
            parse_mode="Markdown",
            reply_to_message_id=announcement_msg_id,
        )
    except TelegramError as e:
        logger.error("R1: failed to post result to channel %s: %s", channel_id, e)


# ---------------------------------------------------------------------------
# Step 1 — open_r1_battles  (8:00pm scheduler job)
# ---------------------------------------------------------------------------

async def open_r1_battles(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Called by scheduler at 8:00pm HKT.
    Groups active students per (class, tier), picks one shared question per group,
    creates DB records, sends DMs and channel headers.
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("R1: DB pool not available")
        return

    bot = context.bot

    try:
        students = await db.get_active_students_with_class(pool)
        if not students:
            logger.info("R1: no active students — skipping")
            return

        # Group by (class_id, tier)
        buckets: Dict[tuple, List[Dict]] = {}
        for s in students:
            key = (s["class_id"], s["tier"])
            buckets.setdefault(key, []).append(s)

        today = datetime.now(timezone.utc).date()

        for (class_id, tier), bucket in buckets.items():
            if not bucket:
                continue

            class_info = await db.get_class_by_id(pool, class_id)
            if not class_info:
                logger.warning("R1: class_id %s not found", class_id)
                continue

            channel_id: int = class_info.get("channel_id") or 0
            class_code: str = class_info["class_code"]   # e.g. "P6A"
            grade: str = class_code[:2]                   # e.g. "P6"
            tier_name: str = config.TIER_NAMES.get(tier, "")
            tier_icon: str = config.TIER_ICONS.get(tier, "")

            # Pick one question for all groups in this (class, tier) bucket
            diff_min, diff_max = config.TIER_DIFFICULTY_RANGE[tier]
            question = await db.get_random_question(
                pool, grade=grade, diff_min=diff_min, diff_max=diff_max
            )
            if not question:
                logger.warning("R1: no question for grade=%s tier=%s", grade, tier)
                continue

            question_text: str = q_module.render_question_text(question)
            options: List[str] = question["options"]
            correct_idx: int = question["correct_option_index"]
            correct_label = ["A", "B", "C", "D"][correct_idx]
            correct_text = f"{correct_label}. {options[correct_idx]}"

            # Shuffle bucket → groups of R1_GROUP_SIZE, merge small remainders
            random.shuffle(bucket)
            groups: List[List[Dict]] = []
            i = 0
            while i < len(bucket):
                chunk = bucket[i: i + config.R1_GROUP_SIZE]
                if (
                    len(chunk) < config.R1_GROUP_SIZE
                    and groups
                    and len(groups[-1]) + len(chunk) <= config.R1_MAX_GROUP_SIZE
                ):
                    groups[-1].extend(chunk)
                else:
                    groups.append(chunk)
                i += config.R1_GROUP_SIZE

            # Upsert battle_session for this class/tier/date
            session_id = await db.upsert_battle_session(
                pool,
                class_id=class_id,
                battle_date=today,
                tier=tier,
                question_id=question["id"],
            )

            # Post one channel header per (class, tier)
            header_text = (
                f"{tier_icon} *{class_code} {tier_name}組 — 第一輪開始！*\n\n"
                f"📚 今晚題目已發送到各組成員私訊\n"
                f"最快答對得最多 XP！⚡"
            )
            header_msg: Optional[Message] = None
            if channel_id:
                try:
                    header_msg = await bot.send_message(
                        chat_id=channel_id,
                        text=header_text,
                        parse_mode="Markdown",
                    )
                except TelegramError as e:
                    logger.error("R1: channel header failed (%s): %s", class_code, e)

            # Create each group and DM every member
            for group_members in groups:
                member_ids = [m["id"] for m in group_members]
                opponent_names = ", ".join(m["display_name"] for m in group_members)

                group_id = await db.create_battle_group(
                    pool,
                    session_id=session_id,
                    member_student_ids=member_ids,
                    question_id=question["id"],
                    options=options,
                    correct_option_index=correct_idx,
                    channel_id=channel_id,
                    channel_message_id=header_msg.message_id if header_msg else None,
                )

                keyboard = _r1_keyboard(group_id, options)
                dm_text = (
                    f"⚔️ *第一輪：小組對戰！*\n\n"
                    f"🏫 {class_code} {tier_name}組\n"
                    f"👥 對手：{opponent_names}\n\n"
                    f"📝 *題目：*\n{question_text}\n\n"
                    f"_搶先答對得最多分！只有一次機會！_"
                )

                for member in group_members:
                    try:
                        sent = await bot.send_message(
                            chat_id=member["telegram_id"],
                            text=dm_text,
                            reply_markup=keyboard,
                            parse_mode="Markdown",
                        )
                        await db.set_group_member_dm_message(
                            pool,
                            group_id=group_id,
                            student_id=member["id"],
                            message_id=sent.message_id,
                            chat_id=member["telegram_id"],
                        )
                    except TelegramError as e:
                        logger.error("R1: DM failed student %s: %s", member["id"], e)

        logger.info("R1: open_r1_battles complete")

    except Exception as e:
        logger.exception("R1: open_r1_battles crashed: %s", e)


# ---------------------------------------------------------------------------
# Step 2 — handle_r1_answer  (CallbackQueryHandler)
# ---------------------------------------------------------------------------

async def handle_r1_answer(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Student taps MCQ button in their R1 DM.
    Callback data: CB_R1_ANSWER + "{group_id}_{option_index}"
    e.g.  "r1_ans_42_2"
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
        raw = query.data.replace(config.CB_R1_ANSWER, "", 1)
        group_id_str, opt_str = raw.rsplit("_", 1)
        group_id = int(group_id_str)
        selected_idx = int(opt_str)
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ 無效回應，請重試。")
        return

    # Load student
    student = await db.get_student_by_telegram_id(pool, telegram_id)
    if not student or student["status"] != "active":
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    student_id = student["id"]

    # Load group
    group = await db.get_battle_group(pool, group_id)
    if not group:
        await query.edit_message_text("❌ 找不到比賽記錄。")
        return

    # Verify membership
    member = await db.get_battle_group_member(pool, group_id, student_id)
    if not member:
        await query.edit_message_text("❌ 你不在這個小組。")
        return

    # Already answered?
    if member["answered_at"] is not None:
        await query.answer("你已經作答了！", show_alert=True)
        return

    # Group still open?
    if group["is_closed"]:
        await query.edit_message_text("⏰ 這輪比賽已結束。\n\n請等待下一輪！")
        return

    correct_idx: int = group["correct_option_index"]
    options: List[str] = group["options"]
    is_correct = (selected_idx == correct_idx)

    # Claim finish position atomically (only for correct answers)
    finish_position = 0
    if is_correct:
        finish_position = await db.claim_next_finish_position(pool, group_id)

    # Rewards by position
    xp_earned = config.R1_XP_REWARDS.get(finish_position, config.R1_XP_REWARDS[0])
    coins_earned = config.R1_COIN_REWARDS.get(finish_position, 0)

    # Persist answer
    await db.record_r1_answer(
        pool,
        group_id=group_id,
        student_id=student_id,
        selected_option=selected_idx,
        is_correct=is_correct,
        finish_position=finish_position,
        xp_earned=xp_earned,
        coins_earned=coins_earned,
    )

    # Apply XP/coins to student totals
    new_xp, leveled_up, new_rank = await db.apply_xp_and_coins(
        pool, student_id=student_id, xp=xp_earned, coins=coins_earned
    )

    # Build DM result text
    correct_label = ["A", "B", "C", "D"][correct_idx]
    correct_text = f"{correct_label}. {options[correct_idx]}"

    if is_correct:
        pos_emoji = _position_emoji(finish_position)
        result_text = (
            f"{pos_emoji} *答對了！第 {finish_position} 位！*\n\n"
            f"✅ 正確答案：{correct_text}\n\n"
            f"🎖 +{xp_earned} XP　🪙 +{coins_earned} 硬幣\n"
            f"📊 總 XP：{new_xp}"
        )
        if leveled_up and new_rank:
            result_text += f"\n\n🆙 *升級！你現在是 {new_rank['title_zh']}！*"
    else:
        result_text = (
            f"❌ *答錯了！*\n\n"
            f"✅ 正確答案：{correct_text}\n\n"
            f"🎖 +{xp_earned} XP（參與獎）"
        )

    try:
        await query.edit_message_text(result_text, parse_mode="Markdown")
    except TelegramError:
        pass

    # If all members answered → resolve group and post channel summary
    all_done = await db.check_group_fully_answered(pool, group_id)
    if all_done:
        await _resolve_group(context.bot, pool, group_id, group, options, correct_text)


# ---------------------------------------------------------------------------
# Step 3 — close_r1_battles  (8:15pm scheduler job)
# ---------------------------------------------------------------------------

async def close_r1_battles(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Called by scheduler at 8:15pm HKT.
    Auto-resolves all groups that still have unanswered members.
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("R1 close: DB pool not available")
        return

    bot = context.bot

    try:
        open_groups = await db.get_open_battle_groups(pool)
        logger.info("R1 close: %d open groups to resolve", len(open_groups))

        for group in open_groups:
            group_id: int = group["id"]
            options: List[str] = group["options"]
            correct_idx: int = group["correct_option_index"]
            correct_label = ["A", "B", "C", "D"][correct_idx]
            correct_text = f"{correct_label}. {options[correct_idx]}"

            # Award participation XP to each unanswered member
            unanswered = await db.get_unanswered_group_members(pool, group_id)
            for m in unanswered:
                xp_part = config.R1_XP_REWARDS[0]
                await db.record_r1_answer(
                    pool,
                    group_id=group_id,
                    student_id=m["student_id"],
                    selected_option=None,
                    is_correct=False,
                    finish_position=0,
                    xp_earned=xp_part,
                    coins_earned=0,
                )
                await db.apply_xp_and_coins(
                    pool, student_id=m["student_id"], xp=xp_part, coins=0
                )
                # Edit their pending DM
                if m.get("dm_chat_id") and m.get("dm_message_id"):
                    try:
                        await bot.edit_message_text(
                            chat_id=m["dm_chat_id"],
                            message_id=m["dm_message_id"],
                            text=(
                                f"⏰ *時間到！*\n\n"
                                f"✅ 正確答案：{correct_text}\n\n"
                                f"🎖 +{xp_part} XP（參與獎）"
                            ),
                            parse_mode="Markdown",
                        )
                    except TelegramError:
                        pass

            await _resolve_group(bot, pool, group_id, group, options, correct_text)

        logger.info("R1 close: complete")

    except Exception as e:
        logger.exception("R1 close: crashed: %s", e)


# ---------------------------------------------------------------------------
# Internal — _resolve_group
# ---------------------------------------------------------------------------

async def _resolve_group(
    bot,
    pool,
    group_id: int,
    group: Dict[str, Any],
    options: List[str],
    correct_text: str,
) -> None:
    """
    Atomically mark group closed then post channel result summary.
    db.close_battle_group returns True only once — safe for concurrent calls.
    """
    was_open = await db.close_battle_group(pool, group_id)
    if not was_open:
        return  # Already resolved

    members = await db.get_battle_group_members_with_details(pool, group_id)
    channel_id: int = group.get("channel_id") or 0
    channel_msg_id: Optional[int] = group.get("channel_message_id")

    await _send_result_to_channel(
        bot=bot,
        channel_id=channel_id,
        announcement_msg_id=channel_msg_id,
        members=members,
        correct_answer=correct_text,
    )
