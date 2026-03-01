#!/usr/bin/env python3
"""
main.py — MathBot MVP v2.0
Hong Kong Primary School Math Gamification Bot

Rounds:
  R1  8:00pm  Nightly live group battle (DM + class channel)
  R2  8:15pm  Solo accuracy session (5 questions, difficulty-adaptive)
  R3  anytime Peer challenges (send from R2, receive anytime before midnight)

Handler registration order matters — more-specific patterns must come first.
"""
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import database as db
from utils.scheduler import setup_jobs
from handlers import registration, round1, round2, round3, shop, leaderboard, admin

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    await db.init_db(application)
    logger.info("Database pool initialised")


async def post_shutdown(application: Application) -> None:
    await db.close_db(application)
    logger.info("Database pool closed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set — aborting")
        return
    if not config.DB_NAME or not config.DB_USER:
        logger.error("Database config incomplete — aborting")
        return

    logger.info("Starting MathBot MVP v2.0...")

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ========================================================================
    # Registration  (ConversationHandler — must be first)
    # ========================================================================

    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("start", registration.start_handler)],
            states={
                config.STATE_AWAITING_CLASS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        registration.receive_class_code,
                    )
                ],
                config.STATE_AWAITING_NAME: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        registration.receive_display_name,
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", registration.cancel_registration)],
            name="registration",
            persistent=False,
        )
    )

    # ========================================================================
    # Round 1 — Live Battle callbacks
    # ========================================================================

    application.add_handler(
        CallbackQueryHandler(
            round1.handle_r1_answer,
            pattern=f"^{config.CB_R1_ANSWER}",
        )
    )

    # ========================================================================
    # Round 2 — Solo Session
    # ========================================================================

    # /r2  — start / view current session
    application.add_handler(CommandHandler("r2", round2.start_r2_session))

    # Answer an R2 question
    application.add_handler(
        CallbackQueryHandler(
            round2.handle_r2_answer,
            pattern=f"^{config.CB_R2_ANSWER}",
        )
    )

    # Difficulty adjustment after session completes
    application.add_handler(
        CallbackQueryHandler(
            round2.handle_r2_difficulty_adjust,
            pattern=f"^{config.CB_R2_ADJ}",
        )
    )

    # Select a student to send R3 challenge to (from R2 result screen)
    application.add_handler(
        CallbackQueryHandler(
            round2.handle_r2_send_challenge,
            pattern=f"^{config.CB_R2_TARGET}",
        )
    )

    # ========================================================================
    # Round 3 — Peer Challenges
    # ========================================================================

    # /challenge  — browse targets manually
    application.add_handler(CommandHandler("challenge", round3.show_challenge_targets))

    # Answer an incoming R3 challenge
    application.add_handler(
        CallbackQueryHandler(
            round3.handle_r3_answer,
            pattern=f"^{config.CB_R3_ANSWER}",
        )
    )

    # Forward a received R3 challenge to someone else
    application.add_handler(
        CallbackQueryHandler(
            round3.handle_r3_forward,
            pattern=f"^{config.CB_R3_FORWARD}",
        )
    )

    # ========================================================================
    # Shop & Inventory
    # ========================================================================

    application.add_handler(CommandHandler("shop", shop.show_shop))
    application.add_handler(CommandHandler("inventory", shop.show_inventory))

    application.add_handler(
        CallbackQueryHandler(shop.handle_shop_category, pattern=f"^{config.CB_SHOP_CAT}")
    )
    application.add_handler(
        CallbackQueryHandler(shop.handle_shop_buy, pattern=f"^{config.CB_SHOP_BUY}")
    )
    application.add_handler(
        CallbackQueryHandler(shop.handle_shop_confirm, pattern=f"^{config.CB_SHOP_CONFIRM}")
    )
    application.add_handler(
        CallbackQueryHandler(shop.handle_inventory_use, pattern=f"^{config.CB_INV_USE}")
    )

    # Spy target selection (item effect)
    application.add_handler(
        CallbackQueryHandler(shop.handle_spy_target, pattern=f"^{config.CB_SPY_TARGET}")
    )

    # ========================================================================
    # Leaderboard & Stats
    # ========================================================================

    application.add_handler(CommandHandler("leaderboard", leaderboard.leaderboard_handler))
    application.add_handler(CommandHandler("lb", leaderboard.leaderboard_handler))
    application.add_handler(CommandHandler("stats", leaderboard.my_stats_handler))
    application.add_handler(CommandHandler("rivals", leaderboard.rivals_handler))

    application.add_handler(
        CallbackQueryHandler(
            leaderboard.handle_lb_view,
            pattern=f"^{config.CB_LB_VIEW}",
        )
    )

    # ========================================================================
    # Admin Commands
    # ========================================================================

    application.add_handler(CommandHandler("admin_pending", admin.admin_pending_handler))
    application.add_handler(CommandHandler("admin_approve", admin.admin_approve_handler))
    application.add_handler(CommandHandler("admin_reject", admin.admin_reject_handler))
    application.add_handler(CommandHandler("admin_topic", admin.admin_topic_handler))
    application.add_handler(CommandHandler("admin_stats", admin.admin_stats_handler))
    application.add_handler(CommandHandler("admin_setchannel", admin.admin_set_channel_handler))
    application.add_handler(CommandHandler("admin_reset", admin.admin_reset_handler))

    application.add_handler(
        CallbackQueryHandler(
            admin.admin_approve_callback,
            pattern=f"^{config.CB_ADMIN_APPROVE}",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            admin.admin_topic_toggle_callback,
            pattern=f"^{config.CB_TOPIC_TOGGLE}",
        )
    )

    # ========================================================================
    # Scheduled Jobs
    # ========================================================================

    setup_jobs(application)

    # ========================================================================
    # Start
    # ========================================================================

    logger.info("All handlers registered")
    logger.info(
        "Schedule: R1@%02d:%02d open, R1 close+R2 open@%02d:%02d, R2 close@%02d:%02d, midnight@00:00",
        config.R1_HOUR, config.R1_MINUTE,
        config.R1_HOUR, config.R1_MINUTE + config.R1_DURATION_MINUTES,
        config.R2_CLOSE_HOUR, config.R2_CLOSE_MINUTE,
    )
    logger.info("Admin IDs: %s", config.ADMIN_TELEGRAM_IDS)
    logger.info("Bot is running — press Ctrl+C to stop")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
