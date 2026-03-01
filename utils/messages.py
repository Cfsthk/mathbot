"""
Message templates module
All bot messages in Cantonese (Traditional Chinese)
"""
from typing import List, Dict, Any
from game import ranks


# ============================================================================
# Registration & Onboarding Messages
# ============================================================================

MSG_WELCOME = """你好！我係數學挑戰機械人 🤖

請輸入你的班別密碼加入遊戲！
例如：P5A、P6B"""

MSG_REGISTER_SUCCESS = """✅ 已收到你的申請！

請等候老師批准。
批准後你就可以開始每日數學挑戰！"""

MSG_APPROVED = """🎉 老師已批准你加入！

歡迎成為 *{rank_zh}*！

每日晚上 7 時正會收到今日題目，加油！💪"""

MSG_NOT_REGISTERED = """❌ 你未登記。

請輸入 /start 開始登記。"""

MSG_NOT_APPROVED = """⏳ 你的帳號仍在審核中

請耐心等候老師批准。"""

MSG_INVALID_CLASS_CODE = """❌ 無效的班別代號

請輸入正確的班別，例如：P5A、P6B"""

MSG_ALREADY_REGISTERED = """✅ 你已經登記了！

使用 /stats 查看你的資料。"""


# ============================================================================
# Daily Question Messages
# ============================================================================

MSG_DAILY_QUESTION = """📚 *今日數學挑戰*

{question}

請選擇答案："""

MSG_DAILY_CORRECT = """✅ *答對了！*

+{xp} XP
+{coins} 硬幣 🪙

{streak_msg}

{unlock_msg}"""

MSG_DAILY_WRONG = """❌ 答錯了！

再試一次。
剩餘機會：{attempts_left}"""

MSG_DAILY_LOCKED = """😢 今日題目已用盡機會

正確答案係：{correct_answer}

明天再來吧！加油！💪"""

MSG_DAILY_ALREADY_DONE = """✅ 你今日已完成題目！

明天 7:00 PM 再來挑戰新題目。

使用 /stats 查看你的進度。"""

MSG_NO_DAILY_QUESTION = """⏰ 今日題目仍未發出

請等候晚上 7 時正。"""


# ============================================================================
# Streak Messages
# ============================================================================

MSG_STREAK = """🔥 *連續答對 {streak} 日！*

獎勵加成：+{bonus}% XP"""

MSG_STREAK_BONUS_COINS = """💰 連勝獎勵：+{coins} 硬幣！"""

MSG_STREAK_BADGE = """🏅 獲得徽章：{badge_name}"""

MSG_STREAK_BROKEN = """💔 連勝記錄中斷了

重新開始累積吧！"""


# ============================================================================
# Challenge Messages
# ============================================================================

MSG_CHALLENGE_SELECT_TARGET = """⚔️ *選擇挑戰對象*

以下係你附近排名的同學：

{target_list}

點擊挑戰！"""

MSG_CHALLENGE_SENT = """⚔️ *挑戰已發出！*

等待 *{name}* 回應中...

對方有 6 小時作答時間。"""

MSG_CHALLENGE_RECEIVED = """⚔️ *{name} 向你發出挑戰！*

你有 *6 小時*作答。
挑戰包含 3 條題目。

{twist_msg}

準備好了嗎？"""

MSG_CHALLENGE_ACCEPT = """💪 開始挑戰！

{twist_warning}

第一題即將開始..."""

MSG_NO_CHALLENGE_UNLOCK = """🔒 挑戰功能未解鎖

繼續累積 XP 到 100 分即可解鎖挑戰功能！

當前 XP：{xp}
需要：100"""

MSG_NO_TARGETS = """❌ 暫時無合適的挑戰對象

請繼續完成每日題目，提升排名後再試。"""

MSG_CHALLENGE_COOLDOWN = """⏰ 挑戰冷卻中

你可以在 {hours} 小時後再發起挑戰。"""


# ============================================================================
# Gauntlet (3-Question Challenge) Messages
# ============================================================================

MSG_GAUNTLET_Q = """🎯 *第 {num} 題（共 3 題）*

{question}

請選擇答案："""

MSG_GAUNTLET_CORRECT = """✅ 答對！

繼續加油！"""

MSG_GAUNTLET_WRONG = """❌ 答錯了！

正確答案：{correct_answer}

挑戰失敗。"""

MSG_GAUNTLET_COMPLETE = """🎊 *全部答對！*

挑戰成功！
等待結果..."""


# ============================================================================
# Challenge Outcome Messages
# ============================================================================

MSG_CHALLENGE_WIN = """🏆 *你贏了！*

對手：{opponent}

獎勵：
+{xp} XP
+{coins} 硬幣 🪙

{rank_msg}"""

MSG_CHALLENGE_LOSE = """😔 *挑戰失敗*

對手：{opponent}

安慰獎：
+{xp} XP

繼續努力！"""

MSG_DEFEND_WIN = """🛡️ *成功守住挑戰！*

挑戰者：{opponent}

獎勵：
+{xp} XP
+{coins} 硬幣 🪙

{rank_msg}"""

MSG_DEFEND_LOSE = """😔 *防守失敗*

挑戰者：{opponent}

安慰獎：
+{xp} XP"""

MSG_CHALLENGE_EXPIRED = """⏰ *挑戰逾時！*

{defender} 未有在時限內回應。

{challenger} 自動勝出。
+{xp} XP
+{coins} 硬幣 🪙"""

MSG_CHALLENGE_TIMEOUT_DEFENDER = """⏰ 你未有在時限內完成挑戰

挑戰者 {challenger} 自動勝出。

記得盡快回應挑戰！"""


# ============================================================================
# Rank Up Messages
# ============================================================================

MSG_RANK_UP = """🎊 *恭喜升級！*

你現在係 *{rank_zh}*！{stars}

解鎖新功能：
{unlocks}

繼續努力！"""


# ============================================================================
# Leaderboard Messages
# ============================================================================

MSG_LEADERBOARD_HEADER = """🏅 *{grade} 排行榜*

"""

MSG_MY_STATS = """📊 *你的資料*

👤 姓名：{name}
🏆 排名：{rank_zh}
📍 位置：第 {position} 位
✨ XP：{xp}
🪙 硬幣：{coins}
🔥 連勝：{streak} 日

{progress}"""

MSG_RIVALS = """⚔️ *附近對手*

{rivals_list}

你可以挑戰排名接近的同學！"""


# ============================================================================
# Boss Battle Messages
# ============================================================================

MSG_BOSS_ANNOUNCED = """👾 *神秘 Boss 出現了！*

{title}

{question}

答對即可獲得：
✨ {xp} XP
🪙 {coins} 硬幣

限時 24 小時，加油！💪"""

MSG_BOSS_CORRECT = """🎉 *你成功挑戰 Boss！*

獎勵：
+{xp} XP
+{coins} 硬幣 🪙

你真係好犀利！"""

MSG_BOSS_WRONG = """😔 Boss 太強了！

正確答案：{correct_answer}

下次繼續努力！"""

MSG_BOSS_ALREADY_ATTEMPTED = """❌ 你已經挑戰過呢個 Boss

每個 Boss 只可以挑戰一次。"""

MSG_NO_ACTIVE_BOSS = """😴 暫時無 Boss 戰

請留意老師公佈！"""


# ============================================================================
# Admin Messages
# ============================================================================

MSG_ADMIN_ONLY = """❌ 此指令只限老師使用"""

MSG_ADMIN_PENDING_LIST = """📋 *待批准學生*

{student_list}

使用 /admin_approve <telegram_id> 批准學生"""

MSG_NO_PENDING = """✅ 暫時無待批准的學生"""

MSG_STUDENT_APPROVED_ADMIN = """✅ 已批准學生

姓名：{name}
班別：{class_code}

學生將會收到通知。"""

MSG_STUDENT_NOT_FOUND = """❌ 找不到該學生"""

MSG_TOPIC_UPDATED = """✅ 已更新題目範圍！

活躍題目範圍：
{topics}"""

MSG_ADMIN_STATS = """📊 *系統統計*

👥 總學生數：{total_students}
✅ 今日活躍：{daily_active}
⚔️ 今日挑戰：{challenges_today}
⏳ 待批准：{pending_approvals}

系統運作正常 ✓"""

MSG_BOSS_CREATED = """✅ Boss 戰已建立！

標題：{title}
獎勵：{xp} XP + {coins} 硬幣
期限：{hours} 小時

已通知所有學生。"""


# ============================================================================
# Shop Messages
# ============================================================================

MSG_SHOP_NOT_UNLOCKED = """🔒 商店未解鎖

升級到 *代數高手* (Rank 4) 即可解鎖商店！

當前排名：{rank_zh}"""

MSG_SHOP_MENU = """🏪 *道具商店*

你的硬幣：{coins} 🪙

{items_list}

使用 /buy <編號> 購買道具"""

MSG_ITEM_PURCHASED = """✅ 成功購買！

{item_name}
-{cost} 硬幣

餘額：{balance} 🪙"""

MSG_NOT_ENOUGH_COINS = """❌ 硬幣不足

需要：{cost} 🪙
你有：{balance} 🪙

繼續完成挑戰賺取硬幣！"""

MSG_INVENTORY = """🎒 *你的道具*

{items_list}

使用 /use <編號> 使用道具"""


# ============================================================================
# Error Messages
# ============================================================================

MSG_ERROR_GENERIC = """❌ 發生錯誤

請稍後再試或聯絡老師。"""

MSG_DATABASE_ERROR = """❌ 資料庫錯誤

請聯絡老師。"""

MSG_NO_QUESTION_AVAILABLE = """❌ 暫時無可用題目

請聯絡老師。"""


# ============================================================================
# Helper Functions
# ============================================================================

def format_leaderboard(students: List[Dict[str, Any]], grade: str) -> str:
    """
    Format leaderboard for a grade
    
    Args:
        students: List of student dicts sorted by XP
        grade: Grade level (P5 or P6)
    
    Returns:
        Formatted leaderboard string
    """
    if not students:
        return MSG_LEADERBOARD_HEADER.format(grade=grade) + "\n暫時無學生。"
    
    msg = MSG_LEADERBOARD_HEADER.format(grade=grade)
    
    # Show top 10
    for i, student in enumerate(students[:10], 1):
        rank_display = ranks.format_rank_display(student)
        
        # Medal for top 3
        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "
        
        msg += f"{medal}{i}. {student['display_name']}\n"
        msg += f"   {rank_display} • {student['xp']} XP\n\n"
    
    return msg


def format_target_list(targets: List[Dict[str, Any]], challenger_rank_pos: int) -> str:
    """
    Format list of challenge targets with inline keyboard data
    
    Args:
        targets: List of student dicts
        challenger_rank_pos: Challenger's rank position
    
    Returns:
        Formatted target list string
    """
    if not targets:
        return "暫無合適對象"
    
    msg = ""
    for target in targets:
        rank_display = ranks.format_rank_display(target)
        
        # Show position relative to challenger
        # Note: Lower position number = higher rank
        if target['xp'] > 0:  # Assume position already calculated
            msg += f"• {target['display_name']}\n"
            msg += f"  {rank_display} • {target['xp']} XP\n\n"
    
    return msg


def format_streak_message(streak: int) -> str:
    """
    Format streak message with bonus info
    
    Args:
        streak: Streak days
    
    Returns:
        Formatted message
    """
    if streak < 3:
        return ""
    
    # Find applicable bonus
    bonus_percent = 0
    for threshold in sorted([3, 5, 7, 14], reverse=True):
        if streak >= threshold:
            bonus_percent = {3: 10, 5: 20, 7: 30, 14: 30}[threshold]
            break
    
    msg = MSG_STREAK.format(streak=streak, bonus=bonus_percent)
    
    # Add coin bonus if applicable
    if streak >= 5:
        bonus_coins = 10
        msg += "\n" + MSG_STREAK_BONUS_COINS.format(coins=bonus_coins)
    
    return msg


def format_rank_up_message(rank_tier: Dict[str, Any]) -> str:
    """
    Format rank up message
    
    Args:
        rank_tier: Rank tier dict from config
    
    Returns:
        Formatted message
    """
    from game.ranks import format_unlocks_list
    
    stars = '⭐' * rank_tier['rank']
    unlocks = format_unlocks_list(rank_tier['unlocks'])
    
    return MSG_RANK_UP.format(
        rank_zh=rank_tier['title_zh'],
        stars=stars,
        unlocks=unlocks
    )


def format_pending_students(students: List[Dict[str, Any]]) -> str:
    """
    Format pending students list for admin
    
    Args:
        students: List of pending student dicts
    
    Returns:
        Formatted list
    """
    if not students:
        return MSG_NO_PENDING
    
    msg = MSG_ADMIN_PENDING_LIST.format(student_list="")
    
    for student in students:
        msg += f"\n👤 {student['display_name']}\n"
        msg += f"   班別：{student['class_code']}\n"
        msg += f"   Telegram ID：`{student['telegram_id']}`\n"
        msg += f"   申請時間：{student['joined_at'].strftime('%Y-%m-%d %H:%M')}\n"
    
    return msg


def format_challenge_unlock_msg(rank_num: int) -> str:
    """
    Format message about challenge unlock
    
    Args:
        rank_num: Student's rank number
    
    Returns:
        Unlock message or empty string
    """
    if rank_num >= 2:
        return "你已解鎖挑戰模式！想挑戰同學嗎？\n使用 /challenge 開始"
    else:
        return ""
