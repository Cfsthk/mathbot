"""
utils/nightly.py — MathBot MVP v2.0
Nightly utility jobs called by scheduler.py:

  send_r1_reminder()          — 19:45 channel reminder
  midnight_reset()            — 00:00 expire R3, reset flags, snapshot, badges
  weekly_tournament_resolve() — 00:05 Sunday: resolve class+grade tournaments
  weekly_tournament_start()   — 00:10 Monday: open new weekly tournaments
"""
import logging
from datetime import datetime, timezone, timedelta

import pytz
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db

logger = logging.getLogger(__name__)

HKT = pytz.timezone(config.TIMEZONE)


# ---------------------------------------------------------------------------
# 19:45 — R1 Reminder
# ---------------------------------------------------------------------------

async def send_r1_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send a 15-minute warning to every active class channel before R1 opens.
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("R1 reminder: no DB pool")
        return

    bot = context.bot
    reminder_text = (
        "⏰ *第一輪即將開始！*\n\n"
        "15 分鐘後小組對戰正式開始！\n"
        "請確保 Telegram 通知已開啟 📲"
    )

    try:
        classes = await db.get_all_classes(pool)
        for cls in classes:
            channel_id = cls.get("channel_id") or 0
            if not channel_id:
                continue
            try:
                await bot.send_message(
                    chat_id=channel_id,
                    text=reminder_text,
                    parse_mode="Markdown",
                )
            except TelegramError as e:
                logger.warning("R1 reminder: failed for class %s: %s", cls["class_code"], e)

        logger.info("R1 reminder: sent to all class channels")

    except Exception as e:
        logger.exception("R1 reminder: crashed: %s", e)


# ---------------------------------------------------------------------------
# 00:00 — Midnight Reset
# ---------------------------------------------------------------------------

async def midnight_reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    00:00 HKT nightly maintenance:
      1. Expire pending R3 challenges (mark expired)
      2. Reset nightly per-student flags (shield_active, trap_active,
         double_down_active, extension_used, r3_sent_count, r3_received_count)
      3. Take nightly XP snapshot for each active student
      4. Detect and award streak badges
      5. Detect and award activity badges (first_blood, perfectionist, etc.)
    """
    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("midnight_reset: no DB pool")
        return

    bot = context.bot
    today = datetime.now(timezone.utc).date()

    try:
        # 1. Expire stale R3 challenges
        expired_count = await db.expire_old_challenges(pool)
        logger.info("midnight_reset: expired %d R3 challenges", expired_count)

        # 2. Reset nightly student flags
        await db.reset_nightly_student_flags(pool)
        logger.info("midnight_reset: nightly flags reset")

        # 3. Snapshot XP for all active students
        students = await db.get_active_students(pool)
        for s in students:
            await db.upsert_nightly_snapshot(
                pool,
                student_id=s["id"],
                snapshot_date=today,
                xp=s["xp"],
                coins=s["coins"],
                rank_num=s["rank_num"],
                tier=s["tier"],
            )
        logger.info("midnight_reset: snapshots taken for %d students", len(students))

        # 4. Check and award streak badges
        for s in students:
            streak = s.get("current_streak", 0)
            for threshold, bonus in config.STREAK_BONUSES.items():
                badge_key = bonus.get("badge")
                if badge_key and streak >= threshold:
                    await db.award_badge_if_missing(pool, s["id"], badge_key)

        # 5. Check and award other badges
        await _check_and_award_activity_badges(pool, bot, students, today)

        logger.info("midnight_reset: complete")

    except Exception as e:
        logger.exception("midnight_reset: crashed: %s", e)


async def _check_and_award_activity_badges(pool, bot, students, today) -> None:
    """Award first_blood, perfectionist, social, and class_pride badges."""
    for s in students:
        student_id = s["id"]

        # first_blood: answered correctly in R1 as position 1 today
        first_blood = await db.check_first_blood_today(pool, student_id, today)
        if first_blood:
            awarded = await db.award_badge_if_missing(pool, student_id, "first_blood")
            if awarded:
                await _notify_badge(bot, s["telegram_id"], "first_blood", "⚡ 先鋒勇士")

        # perfectionist: 100% accuracy in R2 today
        perfect = await db.check_r2_perfect_today(pool, student_id, today)
        if perfect:
            awarded = await db.award_badge_if_missing(pool, student_id, "perfectionist")
            if awarded:
                await _notify_badge(bot, s["telegram_id"], "perfectionist", "🎯 完美主義者")

        # social_butterfly: sent R3 challenge 5+ days in a week
        social = await db.check_social_butterfly(pool, student_id)
        if social:
            awarded = await db.award_badge_if_missing(pool, student_id, "social_butterfly")
            if awarded:
                await _notify_badge(bot, s["telegram_id"], "social_butterfly", "🦋 社交達人")


async def _notify_badge(bot, telegram_id: int, badge_key: str, badge_name: str) -> None:
    """DM a student about a newly earned badge."""
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"🏅 *新徽章解鎖：{badge_name}！*\n\n使用 /stats 查看所有徽章。",
            parse_mode="Markdown",
        )
    except TelegramError as e:
        logger.warning("Badge notify failed for %s (%s): %s", telegram_id, badge_key, e)


# ---------------------------------------------------------------------------
# 00:05 — Weekly Tournament Resolve (Sundays)
# ---------------------------------------------------------------------------

async def weekly_tournament_resolve(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Runs every day at 00:05 but only acts on Sundays (HKT).
    Resolves the class and grade weekly tournaments:
      - Ranks classes by average XP gained this week
      - Distributes coin prizes to top-3 per tournament
      - Announces results to grade channel
    """
    now_hkt = datetime.now(HKT)
    if now_hkt.weekday() != config.WEEKLY_RESOLVE_DAY:
        return  # Not Sunday

    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("weekly_tournament_resolve: no DB pool")
        return

    bot = context.bot

    try:
        grades = config.VALID_GRADES
        for grade in grades:
            # Resolve class tournament for this grade
            results = await db.resolve_class_tournament(pool, grade)
            if not results:
                continue

            # Award prizes
            prizes = config.TOURNAMENT_PRIZES_CLASS
            for i, cls_result in enumerate(results[:3]):
                prize_coins = prizes[i] if i < len(prizes) else 0
                if prize_coins:
                    await db.award_tournament_prize_to_class(
                        pool, cls_result["class_id"], prize_coins
                    )

            # Announce to grade channel
            grade_channel = await db.get_grade_channel(pool, grade)
            if grade_channel:
                text = _format_tournament_results(grade, results, prizes, "班際")
                try:
                    await bot.send_message(
                        chat_id=grade_channel,
                        text=text,
                        parse_mode="Markdown",
                    )
                except TelegramError as e:
                    logger.error("Tournament resolve announce failed (%s): %s", grade, e)

        logger.info("weekly_tournament_resolve: complete")

    except Exception as e:
        logger.exception("weekly_tournament_resolve: crashed: %s", e)


# ---------------------------------------------------------------------------
# 00:10 — Weekly Tournament Start (Mondays)
# ---------------------------------------------------------------------------

async def weekly_tournament_start(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Runs every day at 00:10 but only acts on Mondays (HKT).
    Opens a new weekly tournament for each grade and announces it.
    """
    now_hkt = datetime.now(HKT)
    if now_hkt.weekday() != config.WEEKLY_RESET_DAY:
        return  # Not Monday

    pool = context.application.bot_data.get("db")
    if not pool:
        logger.error("weekly_tournament_start: no DB pool")
        return

    bot = context.bot

    try:
        week_start = datetime.now(timezone.utc).date()
        week_end = week_start + timedelta(days=6)

        for grade in config.VALID_GRADES:
            tournament_id = await db.create_weekly_tournament(
                pool,
                grade=grade,
                week_start=week_start,
                week_end=week_end,
                tournament_type="class",
            )

            grade_channel = await db.get_grade_channel(pool, grade)
            if grade_channel:
                text = (
                    f"🏆 *新一週班際競賽開始！*\n\n"
                    f"🎯 {grade} 年級各班，本週誰能奪冠？\n\n"
                    f"獎勵：\n"
                    f"🥇 冠軍班：+{config.TOURNAMENT_PRIZES_CLASS[0]} 硬幣（每位成員）\n"
                    f"🥈 亞軍班：+{config.TOURNAMENT_PRIZES_CLASS[1]} 硬幣\n"
                    f"🥉 季軍班：+{config.TOURNAMENT_PRIZES_CLASS[2]} 硬幣\n\n"
                    f"_每晚完成三輪，為班爭光！加油💪_"
                )
                try:
                    await bot.send_message(
                        chat_id=grade_channel,
                        text=text,
                        parse_mode="Markdown",
                    )
                except TelegramError as e:
                    logger.error("Tournament start announce failed (%s): %s", grade, e)

        logger.info("weekly_tournament_start: complete")

    except Exception as e:
        logger.exception("weekly_tournament_start: crashed: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_tournament_results(
    grade: str,
    results: list,
    prizes: list,
    tournament_type: str,
) -> str:
    """Format weekly tournament result announcement."""
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 *{grade} 年級{tournament_type}競賽結果！*\n"]
    for i, r in enumerate(results[:3]):
        medal = medals[i] if i < len(medals) else "🏅"
        prize = prizes[i] if i < len(prizes) else 0
        lines.append(
            f"{medal} {r['class_code']} — 平均 {r['avg_xp_gained']:.0f} XP"
            + (f"（+{prize} 硬幣獎勵）" if prize else "")
        )
    if len(results) > 3:
        for r in results[3:]:
            lines.append(f"   {r['class_code']} — 平均 {r['avg_xp_gained']:.0f} XP")
    lines.append("\n_下週再接再厲！加油！💪_")
    return "\n".join(lines)
