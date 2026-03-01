"""
Daily question handler module
Handles daily question sending, answering, and streak management
"""
from datetime import date, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
import database as db
from game import questions as q_module
from game import scoring
from game import ranks
from utils import messages as msg
from handlers.registration import check_student_active


async def send_daily_questions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job: Send daily questions to all active students
    Runs at DAILY_SEND_HOUR in HKT timezone
    
    Args:
        context: Job context from JobQueue
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        print("❌ Database pool not available for daily questions")
        return
    
    try:
        # Get all active students
        students = await db.get_active_students(pool)
        
        sent_count = 0
        error_count = 0
        
        for student in students:
            try:
                # Select appropriate question for student
                question = await q_module.select_daily_question(
                    pool,
                    student['id'],
                    student['grade']
                )
                
                if not question:
                    print(f"⚠️ No question available for student {student['id']}")
                    error_count += 1
                    continue
                
                # Generate question params and options
                params = question['generated_params']
                options = question['generated_options']
                correct_index = question['generated_correct_index']
                
                # Render question text
                question_text = q_module.render_question(question, params)
                
                # Log to database
                log_id = await db.log_daily_sent(
                    pool,
                    student['id'],
                    question['id'],
                    params,
                    options,
                    correct_index
                )
                
                # Create inline keyboard with MCQ options
                keyboard = []
                for i, option in enumerate(options):
                    callback_data = f"{config.CB_DAILY_ANSWER}{log_id}_{i}"
                    keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send question to student
                await context.bot.send_message(
                    chat_id=student['telegram_id'],
                    text=msg.MSG_DAILY_QUESTION.format(question=question_text),
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                sent_count += 1
                
            except Exception as e:
                print(f"❌ Error sending to student {student['id']}: {e}")
                error_count += 1
        
        print(f"✅ Daily questions sent: {sent_count} success, {error_count} errors")
        
    except Exception as e:
        print(f"❌ Error in send_daily_questions: {e}")


async def handle_daily_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle student's answer to daily question via inline button callback
    
    Args:
        update: Telegram update with callback query
        context: Bot context
    """
    query = update.callback_query
    await query.answer()
    
    pool = context.application.bot_data.get('db')
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Check if student is active
    student, error = await check_student_active(pool, update.effective_user.id)
    if error:
        await query.edit_message_text(error)
        return
    
    # Parse callback data: "daily_{log_id}_{option_index}"
    try:
        callback_data = query.data
        parts = callback_data.replace(config.CB_DAILY_ANSWER, '').split('_')
        log_id = int(parts[0])
        selected_option = int(parts[1])
    except (ValueError, IndexError):
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Get daily log
    async with pool.acquire() as conn:
        log = await conn.fetchrow(
            "SELECT * FROM daily_logs WHERE id = $1",
            log_id
        )
    
    if not log:
        await query.edit_message_text("❌ 找不到題目記錄")
        return
    
    # Check if already answered correctly
    if log['answered_correctly']:
        await query.edit_message_text(msg.MSG_DAILY_ALREADY_DONE)
        return
    
    # Check if too many attempts
    current_attempts = log['attempts']
    if current_attempts >= (config.DAILY_QUESTION_RETRIES + 1):
        await query.edit_message_text(msg.MSG_DAILY_ALREADY_DONE)
        return
    
    # Increment attempts
    new_attempts = current_attempts + 1
    await db.increment_daily_attempts(pool, student['id'])
    
    # Check if answer is correct
    correct_index = log['correct_index']
    is_correct = q_module.validate_answer(selected_option, correct_index)
    
    if is_correct:
        # Correct answer!
        await handle_correct_daily_answer(
            query, pool, student, log, new_attempts
        )
    else:
        # Wrong answer
        await handle_wrong_daily_answer(
            query, pool, log_id, new_attempts, log['options'][correct_index]
        )


async def handle_correct_daily_answer(query, pool, student: dict, 
                                      log: dict, attempts: int) -> None:
    """
    Handle correct daily answer - update streak, award XP/coins, check badges
    
    Args:
        query: Callback query
        pool: Database pool
        student: Student dict
        log: Daily log record
        attempts: Number of attempts taken
    """
    student_id = student['id']
    today = date.today()
    
    # Update daily log
    await db.update_daily_log_answer(pool, log['id'], True, attempts)
    
    # Calculate streak
    last_daily_date = student['last_daily_date']
    current_streak = student['streak']
    
    if last_daily_date:
        days_diff = (today - last_daily_date).days
        if days_diff == 1:
            # Consecutive day
            new_streak = current_streak + 1
        elif days_diff == 0:
            # Same day (shouldn't happen but handle gracefully)
            new_streak = current_streak
        else:
            # Streak broken
            new_streak = 1
    else:
        # First daily ever
        new_streak = 1
    
    # Update streak in database
    await db.update_student_streak(pool, student_id, new_streak, today)
    
    # Get question difficulty for reward calculation
    question = await db.get_question_by_id(pool, log['question_id'])
    difficulty = question['difficulty'] if question else 1
    
    # Calculate rewards
    rewards = scoring.calculate_daily_rewards(difficulty, new_streak)
    xp_reward = rewards['xp']
    coins_reward = rewards['coins']
    
    # Award XP and coins
    await db.update_student_xp_coins(pool, student_id, xp_reward, coins_reward)
    
    # Check for rank up
    old_xp = student['xp']
    new_xp = old_xp + xp_reward
    rank_up_info = await db.check_and_update_rank(pool, student_id)
    
    # Check for badges
    await check_daily_badges(pool, student_id, new_streak, today)
    
    # Format streak message
    streak_text = msg.format_streak_message(new_streak) if new_streak >= 3 else ""
    
    # Format unlock message
    new_rank = student['rank_num']
    if rank_up_info:
        new_rank = rank_up_info['rank']
    unlock_text = msg.format_challenge_unlock_msg(new_rank)
    
    # Send success message
    response = msg.MSG_DAILY_CORRECT.format(
        xp=xp_reward,
        coins=coins_reward,
        streak_msg=streak_text,
        unlock_msg=unlock_text
    )
    
    # Add rank up message if applicable
    if rank_up_info:
        response += "\n\n" + msg.format_rank_up_message(rank_up_info)
    
    await query.edit_message_text(response, parse_mode='Markdown')
    
    # If challenge unlocked, show challenge button
    if new_rank >= 2:
        keyboard = [[InlineKeyboardButton("⚔️ 挑戰同學", callback_data="show_challenge_menu")]]
        await query.message.reply_text(
            "你可以挑戰其他同學！",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_wrong_daily_answer(query, pool, log_id: int, 
                                    attempts: int, correct_answer: str) -> None:
    """
    Handle wrong daily answer - show retry or lock
    
    Args:
        query: Callback query
        pool: Database pool
        log_id: Daily log ID
        attempts: Number of attempts taken
        correct_answer: The correct answer
    """
    max_attempts = config.DAILY_QUESTION_RETRIES + 1
    attempts_left = max_attempts - attempts
    
    if attempts_left > 0:
        # Still have attempts left
        await query.edit_message_text(
            msg.MSG_DAILY_WRONG.format(attempts_left=attempts_left)
        )
        
        # Re-send the question with options
        async with pool.acquire() as conn:
            log = await conn.fetchrow(
                "SELECT * FROM daily_logs WHERE id = $1",
                log_id
            )
        
        if log:
            # Get question
            question = await db.get_question_by_id(pool, log['question_id'])
            if question:
                question_text = q_module.render_question(question, log['params'])
                options = log['options']
                
                # Recreate keyboard
                keyboard = []
                for i, option in enumerate(options):
                    callback_data = f"{config.CB_DAILY_ANSWER}{log_id}_{i}"
                    keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(
                    f"📚 {question_text}\n\n請選擇答案：",
                    reply_markup=reply_markup
                )
    else:
        # No attempts left
        await db.update_daily_log_answer(pool, log_id, False, attempts)
        
        await query.edit_message_text(
            msg.MSG_DAILY_LOCKED.format(correct_answer=correct_answer)
        )


async def check_daily_badges(pool, student_id: int, streak: int, today: date) -> None:
    """
    Check and award badges for daily question completion
    
    Args:
        pool: Database pool
        student_id: Student ID
        streak: Current streak
        today: Today's date
    """
    # First blood: First student to answer today
    async with pool.acquire() as conn:
        first_today = await conn.fetchval(
            """
            SELECT COUNT(*) FROM daily_logs
            WHERE DATE(sent_at AT TIME ZONE 'Asia/Hong_Kong') = $1
            AND answered_correctly = TRUE
            """,
            today
        )
    
    if first_today == 1:
        await db.award_badge(pool, student_id, 'first_blood')
    
    # Streak badges
    if streak >= 7:
        await db.award_badge(pool, student_id, 'on_fire')
    
    if streak >= 14:
        await db.award_badge(pool, student_id, 'unstoppable')


async def view_daily_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /daily - Show today's daily question status
    
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
    
    # Get today's daily log
    daily_log = await db.get_todays_daily_log(pool, student['id'])
    
    if not daily_log:
        await update.message.reply_text(msg.MSG_NO_DAILY_QUESTION)
        return
    
    if daily_log['answered_correctly']:
        await update.message.reply_text(msg.MSG_DAILY_ALREADY_DONE)
        return
    
    # Re-send the question
    question = await db.get_question_by_id(pool, daily_log['question_id'])
    if not question:
        await update.message.reply_text(msg.MSG_ERROR_GENERIC)
        return
    
    question_text = q_module.render_question(question, daily_log['params'])
    options = daily_log['options']
    
    # Create keyboard
    keyboard = []
    for i, option in enumerate(options):
        callback_data = f"{config.CB_DAILY_ANSWER}{daily_log['id']}_{i}"
        keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    attempts_left = (config.DAILY_QUESTION_RETRIES + 1) - daily_log['attempts']
    
    await update.message.reply_text(
        msg.MSG_DAILY_QUESTION.format(question=question_text) + 
        f"\n\n剩餘機會：{attempts_left}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
