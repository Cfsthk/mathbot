"""
Admin handler module
Handles admin-only commands for teacher/administrator
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
import config
import database as db
from game import questions as q_module
from utils import messages as msg


def is_admin(user_id: int) -> bool:
    """
    Check if user is an admin
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        True if admin, False otherwise
    """
    return user_id in config.ADMIN_TELEGRAM_IDS


async def admin_pending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /admin_pending - List pending student approvals
    
    Args:
        update: Telegram update
        context: Bot context
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Get pending students
    pending = await db.get_pending_students(pool)
    
    if not pending:
        await update.message.reply_text(msg.MSG_NO_PENDING)
        return
    
    # Format pending list
    pending_text = msg.format_pending_students(pending)
    
    # Create inline keyboard for quick approval
    keyboard = []
    for student in pending[:5]:  # Show first 5
        keyboard.append([InlineKeyboardButton(
            f"✅ 批准 {student['display_name']}",
            callback_data=f"{config.CB_ADMIN_APPROVE}{student['telegram_id']}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        pending_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def admin_approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /admin_approve <telegram_id> - Approve a student
    
    Args:
        update: Telegram update
        context: Bot context
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Parse telegram_id from command args
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "用法：/admin_approve <telegram_id>\n\n" +
            "使用 /admin_pending 查看待批准學生"
        )
        return
    
    try:
        telegram_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 無效的 Telegram ID")
        return
    
    # Get student
    student = await db.get_student_by_telegram_id(pool, telegram_id)
    if not student:
        await update.message.reply_text(msg.MSG_STUDENT_NOT_FOUND)
        return
    
    if student['is_active']:
        await update.message.reply_text(f"✅ {student['display_name']} 已經批准了")
        return
    
    # Approve student
    success = await db.approve_student(pool, student['id'])
    
    if success:
        await update.message.reply_text(
            msg.MSG_STUDENT_APPROVED_ADMIN.format(
                name=student['display_name'],
                class_code=student['class_code']
            )
        )
        
        # Notify student
        try:
            from game.ranks import get_rank_tier
            rank = get_rank_tier(0)
            
            await context.bot.send_message(
                chat_id=telegram_id,
                text=msg.MSG_APPROVED.format(rank_zh=rank['title_zh']),
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error notifying student: {e}")
    else:
        await update.message.reply_text(msg.MSG_ERROR_GENERIC)


async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: Approve student via inline button
    
    Args:
        update: Telegram update with callback query
        context: Bot context
    """
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Parse telegram_id from callback data
    try:
        telegram_id = int(query.data.replace(config.CB_ADMIN_APPROVE, ''))
    except ValueError:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Get and approve student
    student = await db.get_student_by_telegram_id(pool, telegram_id)
    if not student:
        await query.edit_message_text(msg.MSG_STUDENT_NOT_FOUND)
        return
    
    await db.approve_student(pool, student['id'])
    
    await query.edit_message_text(
        f"✅ 已批准 {student['display_name']} ({student['class_code']})"
    )
    
    # Notify student
    try:
        from game.ranks import get_rank_tier
        rank = get_rank_tier(0)
        
        await context.bot.send_message(
            chat_id=telegram_id,
            text=msg.MSG_APPROVED.format(rank_zh=rank['title_zh']),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error notifying student: {e}")


async def admin_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /admin_topic - Show topic toggle menu
    
    Args:
        update: Telegram update
        context: Bot context
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Get all topics
    topics = await db.get_all_topics(pool)
    
    # Create inline keyboard
    keyboard = []
    for topic in topics:
        status = "✅" if topic['is_active'] else "❌"
        button_text = f"{status} {topic['name_zh']} ({topic['grade']})"
        callback_data = f"{config.CB_TOPIC_TOGGLE}{topic['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📚 *題目範圍管理*\n\n點擊切換開關：",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def admin_topic_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: Toggle topic active status
    
    Args:
        update: Telegram update with callback query
        context: Bot context
    """
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Parse topic_id from callback data
    try:
        topic_id = int(query.data.replace(config.CB_TOPIC_TOGGLE, ''))
    except ValueError:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Toggle topic
    new_status = await db.toggle_topic(pool, topic_id)
    
    # Refresh topic list
    topics = await db.get_all_topics(pool)
    
    # Recreate keyboard
    keyboard = []
    for topic in topics:
        status = "✅" if topic['is_active'] else "❌"
        button_text = f"{status} {topic['name_zh']} ({topic['grade']})"
        callback_data = f"{config.CB_TOPIC_TOGGLE}{topic['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Get active topics list
    active_topics = [t for t in topics if t['is_active']]
    topics_text = '\n'.join([f"• {t['name_zh']} ({t['grade']})" for t in active_topics])
    
    await query.edit_message_text(
        msg.MSG_TOPIC_UPDATED.format(topics=topics_text),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def admin_boss_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /admin_boss <question_id> <title> - Create boss battle
    
    Args:
        update: Telegram update
        context: Bot context
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Parse arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "用法：/admin_boss <question_id> <boss標題>\n\n" +
            "例如：/admin_boss 1 超級數學魔王"
        )
        return
    
    try:
        question_id = int(context.args[0])
        title = ' '.join(context.args[1:])
    except ValueError:
        await update.message.reply_text("❌ 無效的 question_id")
        return
    
    # Get question
    question = await db.get_question_by_id(pool, question_id)
    if not question:
        await update.message.reply_text(f"❌ 找不到 question_id {question_id}")
        return
    
    # Generate boss question
    params = q_module.generate_question_params(question)
    options, correct_index = q_module.generate_mcq_options(question, params)
    
    # Create boss battle (24 hours duration)
    boss_id = await db.create_boss_battle(
        pool,
        question_id=question_id,
        params=params,
        options=options,
        correct_index=correct_index,
        title_zh=title,
        xp_reward=200,
        coins_reward=100,
        duration_hours=24,
        created_by=update.effective_user.id
    )
    
    await update.message.reply_text(
        msg.MSG_BOSS_CREATED.format(
            title=title,
            xp=200,
            coins=100,
            hours=24
        )
    )
    
    # Broadcast to all active students
    students = await db.get_active_students(pool)
    question_text = q_module.render_question(question, params)
    
    # Create inline keyboard for boss
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(option, callback_data=f"boss_{boss_id}_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sent_count = 0
    for student in students:
        try:
            await context.bot.send_message(
                chat_id=student['telegram_id'],
                text=msg.MSG_BOSS_ANNOUNCED.format(
                    title=title,
                    question=question_text,
                    xp=200,
                    coins=100
                ),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception as e:
            print(f"Error sending boss to student {student['id']}: {e}")
    
    await update.message.reply_text(f"✅ 已通知 {sent_count} 位學生")


async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /admin_stats - Show system statistics
    
    Args:
        update: Telegram update
        context: Bot context
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(msg.MSG_ADMIN_ONLY)
        return
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Get stats
    stats = await db.get_daily_stats(pool)
    
    await update.message.reply_text(
        msg.MSG_ADMIN_STATS.format(
            total_students=stats['total_students'],
            daily_active=stats['daily_active'],
            challenges_today=stats['challenges_today'],
            pending_approvals=stats['pending_approvals']
        ),
        parse_mode='Markdown'
    )
