"""
Registration handler module
Handles /start command and student registration flow
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import config
import database as db
from utils import messages as msg


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command - begin registration or show welcome for existing users
    
    Returns:
        STATE_AWAITING_CLASS_CODE or ConversationHandler.END
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return ConversationHandler.END
    
    user = update.effective_user
    
    # Check if already registered
    student = await db.get_student_by_telegram_id(pool, user.id)
    
    if student:
        if student['is_active']:
            # Already active student
            await update.message.reply_text(msg.MSG_ALREADY_REGISTERED)
            return ConversationHandler.END
        else:
            # Registered but not approved yet
            await update.message.reply_text(msg.MSG_NOT_APPROVED)
            return ConversationHandler.END
    
    # New user - start registration
    await update.message.reply_text(msg.MSG_WELCOME)
    return config.STATE_AWAITING_CLASS_CODE


async def receive_class_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive and validate class code, then ask for display name
    
    Returns:
        STATE_AWAITING_DISPLAY_NAME or STATE_AWAITING_CLASS_CODE
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return ConversationHandler.END
    
    class_code = update.message.text.strip().upper()
    
    # Validate class code
    if class_code not in config.VALID_CLASS_CODES:
        await update.message.reply_text(msg.MSG_INVALID_CLASS_CODE)
        return config.STATE_AWAITING_CLASS_CODE
    
    # Extract grade from class code (e.g., P5A -> P5)
    grade = class_code[:2]
    if grade not in config.VALID_GRADES:
        await update.message.reply_text(msg.MSG_INVALID_CLASS_CODE)
        return config.STATE_AWAITING_CLASS_CODE
    
    # Store class code and grade in context for next step
    context.user_data['class_code'] = class_code
    context.user_data['grade'] = grade
    
    # Ask for display name
    await update.message.reply_text(
        "請輸入你的名稱：\n例如：陳小明"
    )
    return config.STATE_AWAITING_DISPLAY_NAME


async def receive_display_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive display name and create student record
    
    Returns:
        ConversationHandler.END
    """
    pool = context.application.bot_data.get('db')
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return ConversationHandler.END
    
    user = update.effective_user
    display_name = update.message.text.strip()
    
    if not display_name or len(display_name) < 2:
        await update.message.reply_text(
            "❌ 名稱太短，請輸入你的全名："
        )
        return config.STATE_AWAITING_DISPLAY_NAME
    
    # Get stored class code and grade
    class_code = context.user_data.get('class_code')
    grade = context.user_data.get('grade')
    
    if not class_code or not grade:
        # Something went wrong, restart
        await update.message.reply_text(msg.MSG_ERROR_GENERIC)
        return ConversationHandler.END
    
    try:
        # Create student record (pending approval)
        student_id = await db.create_student(
            pool,
            telegram_id=user.id,
            username=user.username or '',
            display_name=display_name,
            class_code=class_code,
            grade=grade
        )
        
        await update.message.reply_text(msg.MSG_REGISTER_SUCCESS)
        
        # Notify admins if configured
        await notify_admins_new_student(
            context,
            display_name,
            class_code,
            user.id
        )
        
        # Clear user data
        context.user_data.clear()
        
    except Exception as e:
        print(f"Error creating student: {e}")
        await update.message.reply_text(msg.MSG_ERROR_GENERIC)
    
    return ConversationHandler.END


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel registration process
    
    Returns:
        ConversationHandler.END
    """
    await update.message.reply_text(
        "已取消登記。\n如需重新登記，請使用 /start"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def notify_admins_new_student(context: ContextTypes.DEFAULT_TYPE, 
                                   name: str, class_code: str, 
                                   telegram_id: int) -> None:
    """
    Notify admin users about new student registration
    
    Args:
        context: Bot context
        name: Student display name
        class_code: Class code
        telegram_id: Student's Telegram ID
    """
    if not config.ADMIN_TELEGRAM_IDS:
        return
    
    notification = f"""📝 *新學生申請*

姓名：{name}
班別：{class_code}
Telegram ID：`{telegram_id}`

使用 /admin_approve {telegram_id} 批准"""
    
    for admin_id in config.ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error notifying admin {admin_id}: {e}")


# Helper function to check if user is registered and active
async def check_student_active(pool, telegram_id: int) -> tuple:
    """
    Check if student is registered and active
    
    Returns:
        Tuple of (student_dict or None, error_message or None)
    """
    student = await db.get_student_by_telegram_id(pool, telegram_id)
    
    if not student:
        return None, msg.MSG_NOT_REGISTERED
    
    if not student['is_active']:
        return None, msg.MSG_NOT_APPROVED
    
    return student, None
