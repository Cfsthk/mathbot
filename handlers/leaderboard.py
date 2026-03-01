"""
Leaderboard and stats handler module
Handles /leaderboard, /stats, /rivals commands
"""
from telegram import Update
from telegram.ext import ContextTypes
import database as db
from game import ranks
from utils import messages as msg
from handlers.registration import check_student_active


async def leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /leaderboard - Show grade leaderboard
    
    Args:
        update: Telegram update
        context: Bot context
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Check if student is active
    student, error = await check_student_active(pool, update.effective_user.id)
    if error:
        await update.message.reply_text(error)
        return
    
    # Get students in same grade
    students = await db.get_active_students(pool, student['grade'])
    
    # Format and send leaderboard
    leaderboard_text = msg.format_leaderboard(students, student['grade'])
    
    await update.message.reply_text(leaderboard_text, parse_mode='Markdown')


async def my_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /stats - Show personal statistics
    
    Args:
        update: Telegram update
        context: Bot context
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Check if student is active
    student, error = await check_student_active(pool, update.effective_user.id)
    if error:
        await update.message.reply_text(error)
        return
    
    # Get rank position
    position = await db.get_student_rank_position(pool, student['id'], student['grade'])
    
    # Get rank display
    rank_display = ranks.format_rank_display(student)
    
    # Get progress to next rank
    progress = ranks.get_rank_progress_bar(student['xp'])
    
    # Format stats message
    stats_text = msg.MSG_MY_STATS.format(
        name=student['display_name'],
        rank_zh=rank_display,
        position=position,
        xp=student['xp'],
        coins=student['coins'],
        streak=student['streak'],
        progress=progress
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')


async def rivals_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /rivals - Show nearby rivals
    
    Args:
        update: Telegram update
        context: Bot context
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Check if student is active
    student, error = await check_student_active(pool, update.effective_user.id)
    if error:
        await update.message.reply_text(error)
        return
    
    # Get nearby students
    rivals = await db.get_nearby_students(pool, student['id'], 5)
    
    if not rivals:
        await update.message.reply_text(
            "暫時無附近對手。\n繼續完成每日題目提升排名！"
        )
        return
    
    # Format rivals list
    rivals_list = ""
    for rival in rivals[:6]:  # Show max 6
        rival_pos = await db.get_student_rank_position(pool, rival['id'], rival['grade'])
        rank_display = ranks.format_rank_display(rival)
        
        rivals_list += f"• {rival['display_name']}\n"
        rivals_list += f"  第 {rival_pos} 位 • {rank_display}\n"
        rivals_list += f"  {rival['xp']} XP\n\n"
    
    await update.message.reply_text(
        msg.MSG_RIVALS.format(rivals_list=rivals_list),
        parse_mode='Markdown'
    )
