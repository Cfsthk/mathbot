"""
Challenge handler module
Handles player-vs-player gauntlet challenges
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
import config
import database as db
from game import questions as q_module
from game import scoring
from game import twists as twist_module
from utils import messages as msg
from handlers.registration import check_student_active


async def show_challenge_targets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command handler: /challenge - Show available challenge targets
    
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
    
    # Check if challenge is unlocked
    if student['rank_num'] < 2:
        xp_needed = 100 - student['xp']
        await update.message.reply_text(
            msg.MSG_NO_CHALLENGE_UNLOCK.format(xp=student['xp'])
        )
        return
    
    # Get nearby students for challenge
    targets = await db.get_nearby_students(
        pool,
        student['id'],
        config.CHALLENGE_RANK_WINDOW
    )
    
    if not targets:
        await update.message.reply_text(msg.MSG_NO_TARGETS)
        return
    
    # Create inline keyboard with targets
    keyboard = []
    challenger_pos = await db.get_student_rank_position(pool, student['id'], student['grade'])
    
    for target in targets[:10]:  # Limit to 10 targets
        target_pos = await db.get_student_rank_position(pool, target['id'], target['grade'])
        
        # Format button text
        from game.ranks import format_rank_display
        rank_display = format_rank_display(target)
        button_text = f"{target['display_name']} ({target['xp']} XP)"
        
        callback_data = f"{config.CB_CHALLENGE_TARGET}{target['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    target_list_text = msg.format_target_list(targets, challenger_pos)
    
    await update.message.reply_text(
        msg.MSG_CHALLENGE_SELECT_TARGET.format(target_list=target_list_text),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def select_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: User selects a challenge target
    Shows twist selection menu
    
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
    
    # Parse target ID from callback data
    try:
        target_id = int(query.data.replace(config.CB_CHALLENGE_TARGET, ''))
    except ValueError:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Get target student
    target = await db.get_student_by_id(pool, target_id)
    if not target:
        await query.edit_message_text("❌ 找不到該同學")
        return
    
    # Store target in context
    context.user_data['challenge_target_id'] = target_id
    
    # Show twist selection if unlocked
    if student['rank_num'] >= 3:
        available_twists = twist_module.get_available_twists(student['rank_num'])
        
        keyboard = []
        for twist in available_twists:
            callback_data = f"{config.CB_CHALLENGE_TWIST}{twist['id']}"
            keyboard.append([InlineKeyboardButton(
                twist['name_zh'],
                callback_data=callback_data
            )])
        
        # Option to skip twist
        keyboard.append([InlineKeyboardButton(
            "不使用特殊規則",
            callback_data=f"{config.CB_CHALLENGE_TWIST}0"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚔️ *挑戰對象：{target['display_name']}*\n\n" +
            twist_module.format_twist_menu(student['rank_num']),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # No twist available, confirm directly
        context.user_data['challenge_twist_id'] = None
        await confirm_challenge(update, context, query)


async def select_twist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: User selects a twist (or none)
    Confirms challenge creation
    
    Args:
        update: Telegram update with callback query
        context: Bot context
    """
    query = update.callback_query
    await query.answer()
    
    # Parse twist ID from callback data
    try:
        twist_id = int(query.data.replace(config.CB_CHALLENGE_TWIST, ''))
        if twist_id == 0:
            twist_id = None
    except ValueError:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Store twist in context
    context.user_data['challenge_twist_id'] = twist_id
    
    await confirm_challenge(update, context, query)


async def confirm_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           query=None) -> None:
    """
    Create challenge and send to defender
    
    Args:
        update: Telegram update
        context: Bot context
        query: Optional callback query
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        if query:
            await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Get student
    student, error = await check_student_active(pool, update.effective_user.id)
    if error:
        if query:
            await query.edit_message_text(error)
        return
    
    target_id = context.user_data.get('challenge_target_id')
    twist_id = context.user_data.get('challenge_twist_id')
    
    if not target_id:
        if query:
            await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    target = await db.get_student_by_id(pool, target_id)
    if not target:
        if query:
            await query.edit_message_text("❌ 找不到該同學")
        return
    
    try:
        # Create challenge
        challenge_id = await db.create_challenge(
            pool,
            student['id'],
            target_id,
            twist_id
        )
        
        # Generate 3 gauntlet questions
        base_difficulty = min(student['rank_num'], 3)
        gauntlet_questions = await q_module.get_gauntlet_questions(
            pool,
            target['grade'],
            base_difficulty
        )
        
        # Store questions in challenge
        for q in gauntlet_questions:
            await db.add_challenge_question(
                pool,
                challenge_id,
                q['id'],
                q['generated_params'],
                q['generated_options'],
                q['generated_correct_index'],
                q['gauntlet_order']
            )
        
        # Notify challenger
        if query:
            await query.edit_message_text(
                msg.MSG_CHALLENGE_SENT.format(name=target['display_name'])
            )
        
        # Notify defender
        twist_text = ""
        if twist_id:
            twist_text = "\n\n" + twist_module.format_twist_display(twist_id)
        
        keyboard = [[InlineKeyboardButton(
            "接受挑戰",
            callback_data=f"{config.CB_CHALLENGE_ACCEPT}{challenge_id}"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=target['telegram_id'],
            text=msg.MSG_CHALLENGE_RECEIVED.format(
                name=student['display_name'],
                twist_msg=twist_text
            ),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Clear context
        context.user_data.clear()
        
    except Exception as e:
        print(f"Error creating challenge: {e}")
        if query:
            await query.edit_message_text(msg.MSG_ERROR_GENERIC)


async def accept_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: Defender accepts challenge
    Start gauntlet Question 1
    
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
    
    # Parse challenge ID
    try:
        challenge_id = int(query.data.replace(config.CB_CHALLENGE_ACCEPT, ''))
    except ValueError:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Get challenge
    challenge = await db.get_challenge_by_id(pool, challenge_id)
    if not challenge or challenge['status'] != 'pending':
        await query.edit_message_text("❌ 挑戰已失效")
        return
    
    # Get twist warning if applicable
    twist_warning = ""
    if challenge['twist_id']:
        twist_warning = twist_module.get_twist_warning(challenge['twist_id'])
    
    # Start with question 1
    await send_gauntlet_question(query, context, challenge_id, 1, twist_warning)


async def send_gauntlet_question(query, context: ContextTypes.DEFAULT_TYPE,
                                 challenge_id: int, question_num: int,
                                 initial_msg: str = "") -> None:
    """
    Send a gauntlet question to defender
    
    Args:
        query: Callback query
        context: Bot context
        challenge_id: Challenge ID
        question_num: Question number (1, 2, or 3)
        initial_msg: Optional initial message
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return
    
    # Get challenge questions
    challenge_questions = await db.get_challenge_questions(pool, challenge_id)
    
    if question_num > len(challenge_questions):
        # All questions answered correctly - defender wins!
        await finalize_challenge_defender_win(query, context, challenge_id)
        return
    
    cq = challenge_questions[question_num - 1]
    
    # Get question details
    question = await db.get_question_by_id(pool, cq['question_id'])
    if not question:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    question_text = q_module.render_question(question, cq['params'])
    options = cq['options']
    
    # Create inline keyboard
    keyboard = []
    for i, option in enumerate(options):
        callback_data = f"{config.CB_GAUNTLET_ANSWER}{cq['id']}_{i}_{question_num}"
        keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = ""
    if initial_msg:
        message_text = initial_msg + "\n\n"
    
    message_text += msg.MSG_GAUNTLET_Q.format(
        num=question_num,
        question=question_text
    )
    
    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_gauntlet_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler: Defender answers gauntlet question
    
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
    
    # Parse callback data: "gaunt_{cq_id}_{option}_{question_num}"
    try:
        parts = query.data.replace(config.CB_GAUNTLET_ANSWER, '').split('_')
        cq_id = int(parts[0])
        selected_option = int(parts[1])
        question_num = int(parts[2])
    except (ValueError, IndexError):
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    # Get challenge question
    async with pool.acquire() as conn:
        cq = await conn.fetchrow(
            "SELECT * FROM challenge_questions WHERE id = $1",
            cq_id
        )
    
    if not cq:
        await query.edit_message_text(msg.MSG_ERROR_GENERIC)
        return
    
    challenge_id = cq['challenge_id']
    
    # Check answer
    is_correct = q_module.validate_answer(selected_option, cq['correct_index'])
    
    # Update challenge question
    await db.update_challenge_question_answer(pool, cq_id, is_correct)
    
    if is_correct:
        # Correct! Move to next question or finish
        await query.edit_message_text(msg.MSG_GAUNTLET_CORRECT)
        
        # Small delay before next question
        import asyncio
        await asyncio.sleep(1)
        
        # Send next question
        await send_gauntlet_question(query, context, challenge_id, question_num + 1)
    else:
        # Wrong answer - challenger wins
        correct_answer = cq['options'][cq['correct_index']]
        await query.edit_message_text(
            msg.MSG_GAUNTLET_WRONG.format(correct_answer=correct_answer)
        )
        
        # Finalize challenge - challenger wins
        await finalize_challenge_challenger_win(query, context, challenge_id)


async def finalize_challenge_defender_win(query, context: ContextTypes.DEFAULT_TYPE,
                                         challenge_id: int) -> None:
    """
    Finalize challenge with defender winning (answered all 3 correctly)
    
    Args:
        query: Callback query
        context: Bot context
        challenge_id: Challenge ID
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        return
    
    # Resolve challenge outcome
    result = await scoring.resolve_challenge_outcome(pool, challenge_id, 'defender')
    
    # Notify defender
    rank_msg = ""
    if result['defender'].get('rank_up'):
        rank_msg = "\n\n" + msg.format_rank_up_message(result['defender']['rank_up'])
    
    await query.message.reply_text(
        msg.MSG_DEFEND_WIN.format(
            opponent=result['challenger']['name'],
            xp=result['defender']['xp'],
            coins=result['defender']['coins'],
            rank_msg=rank_msg
        ),
        parse_mode='Markdown'
    )
    
    # Notify challenger
    try:
        await context.bot.send_message(
            chat_id=result['challenger']['id'],
            text=msg.MSG_CHALLENGE_LOSE.format(
                opponent=result['defender']['name'],
                xp=result['challenger']['xp']
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error notifying challenger: {e}")


async def finalize_challenge_challenger_win(query, context: ContextTypes.DEFAULT_TYPE,
                                           challenge_id: int) -> None:
    """
    Finalize challenge with challenger winning (defender got one wrong)
    
    Args:
        query: Callback query
        context: Bot context
        challenge_id: Challenge ID
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        return
    
    # Resolve challenge outcome
    result = await scoring.resolve_challenge_outcome(pool, challenge_id, 'challenger')
    
    # Notify defender
    await query.message.reply_text(
        msg.MSG_DEFEND_LOSE.format(
            opponent=result['challenger']['name'],
            xp=result['defender']['xp']
        ),
        parse_mode='Markdown'
    )
    
    # Notify challenger
    rank_msg = ""
    if result['challenger'].get('rank_up'):
        rank_msg = "\n\n" + msg.format_rank_up_message(result['challenger']['rank_up'])
    
    try:
        await context.bot.send_message(
            chat_id=result['challenger']['id'],
            text=msg.MSG_CHALLENGE_WIN.format(
                opponent=result['defender']['name'],
                xp=result['challenger']['xp'],
                coins=result['challenger']['coins'],
                rank_msg=rank_msg
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error notifying challenger: {e}")


async def check_expired_challenges(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job: Check and expire old challenges
    Runs every 30 minutes
    
    Args:
        context: Job context
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        print("❌ Database pool not available for challenge expiry check")
        return
    
    try:
        # Get expired challenge IDs
        expired_ids = await db.expire_old_challenges(pool)
        
        if not expired_ids:
            return
        
        print(f"⏰ Expiring {len(expired_ids)} challenges")
        
        # Process each expired challenge
        for challenge_id in expired_ids:
            try:
                # Resolve as timeout win for challenger
                result = await scoring.resolve_challenge_outcome(pool, challenge_id, 'timeout')
                
                # Notify both players
                await context.bot.send_message(
                    chat_id=result['challenger']['id'],
                    text=msg.MSG_CHALLENGE_EXPIRED.format(
                        defender=result['defender']['name'],
                        challenger=result['challenger']['name'],
                        xp=result['challenger']['xp'],
                        coins=result['challenger']['coins']
                    ),
                    parse_mode='Markdown'
                )
                
                await context.bot.send_message(
                    chat_id=result['defender']['id'],
                    text=msg.MSG_CHALLENGE_TIMEOUT_DEFENDER.format(
                        challenger=result['challenger']['name']
                    ),
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                print(f"Error processing expired challenge {challenge_id}: {e}")
        
    except Exception as e:
        print(f"❌ Error in check_expired_challenges: {e}")
