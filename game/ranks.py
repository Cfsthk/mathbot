"""
Rank tier management module
Handles rank progression, unlocks, and display formatting
"""
from typing import Dict, Any, List, Optional, Tuple
import config


def get_rank_tier(xp: int) -> Dict[str, Any]:
    """
    Get the rank tier for a given XP amount
    
    Args:
        xp: Student's total XP
    
    Returns:
        Rank tier dict from config.RANK_TIERS
    """
    # Find the highest tier the student qualifies for
    current_tier = config.RANK_TIERS[0]  # Default to rank 1
    
    for tier in config.RANK_TIERS:
        if xp >= tier['xp_required']:
            current_tier = tier
        else:
            break
    
    return current_tier


def check_rank_up(old_xp: int, new_xp: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if XP increase resulted in a rank up
    
    Args:
        old_xp: Previous XP amount
        new_xp: New XP amount
    
    Returns:
        Tuple of (ranked_up: bool, new_tier: dict or None)
    """
    old_tier = get_rank_tier(old_xp)
    new_tier = get_rank_tier(new_xp)
    
    if new_tier['rank'] > old_tier['rank']:
        return True, new_tier
    
    return False, None


def get_unlock_list(rank_num: int) -> List[str]:
    """
    Get all unlocks available up to and including this rank
    
    Args:
        rank_num: Rank number (1-6)
    
    Returns:
        List of unlock keys
    """
    all_unlocks = []
    
    for tier in config.RANK_TIERS:
        if tier['rank'] <= rank_num:
            all_unlocks.extend(tier['unlocks'])
        else:
            break
    
    return all_unlocks


def has_unlock(rank_num: int, unlock_key: str) -> bool:
    """
    Check if a rank has access to a specific unlock
    
    Args:
        rank_num: Rank number (1-6)
        unlock_key: Unlock key to check (e.g., 'challenge', 'shop_basic')
    
    Returns:
        True if unlocked, False otherwise
    """
    unlocks = get_unlock_list(rank_num)
    return unlock_key in unlocks


def format_rank_display(student: Dict[str, Any]) -> str:
    """
    Format rank display with stars and Chinese title
    
    Args:
        student: Student dict with rank_num
    
    Returns:
        Formatted rank string (e.g., "代數高手 ⭐⭐⭐⭐")
    """
    rank_num = student.get('rank_num', 1)
    
    # Get rank tier info
    tier = next((t for t in config.RANK_TIERS if t['rank'] == rank_num), config.RANK_TIERS[0])
    
    # Create star display
    stars = '⭐' * rank_num
    
    return f"{tier['title_zh']} {stars}"


def get_next_rank_info(current_xp: int) -> Optional[Dict[str, Any]]:
    """
    Get information about the next rank tier
    
    Args:
        current_xp: Student's current XP
    
    Returns:
        Dict with next rank info and XP needed, or None if max rank
    """
    current_tier = get_rank_tier(current_xp)
    current_rank = current_tier['rank']
    
    # Find next tier
    next_tier = None
    for tier in config.RANK_TIERS:
        if tier['rank'] == current_rank + 1:
            next_tier = tier
            break
    
    if not next_tier:
        return None  # Already at max rank
    
    xp_needed = next_tier['xp_required'] - current_xp
    
    return {
        'tier': next_tier,
        'xp_needed': xp_needed,
        'progress_percent': int((current_xp / next_tier['xp_required']) * 100)
    }


def format_unlocks_list(unlocks: List[str]) -> str:
    """
    Format unlock keys into readable Cantonese text
    
    Args:
        unlocks: List of unlock keys
    
    Returns:
        Formatted string in Cantonese
    """
    unlock_names = {
        'daily': '每日挑戰',
        'challenge': '玩家對戰',
        'twist': '特殊規則',
        'shop_basic': '基本商店',
        'shop_advanced': '進階商店',
        'rival_stats': '對手資料',
        'boss': 'Boss戰',
        'tournament': '錦標賽'
    }
    
    readable = [unlock_names.get(key, key) for key in unlocks]
    return '、'.join(readable)


def get_rank_progress_bar(current_xp: int, width: int = 10) -> str:
    """
    Create a visual progress bar for rank progression
    
    Args:
        current_xp: Student's current XP
        width: Width of progress bar in characters
    
    Returns:
        Progress bar string (e.g., "▰▰▰▰▰▱▱▱▱▱ 50%")
    """
    next_rank = get_next_rank_info(current_xp)
    
    if not next_rank:
        # Max rank reached
        return '▰' * width + ' MAX'
    
    progress_percent = next_rank['progress_percent']
    filled = int((progress_percent / 100) * width)
    empty = width - filled
    
    bar = '▰' * filled + '▱' * empty
    return f"{bar} {progress_percent}%"


def get_rank_by_number(rank_num: int) -> Optional[Dict[str, Any]]:
    """
    Get rank tier info by rank number
    
    Args:
        rank_num: Rank number (1-6)
    
    Returns:
        Rank tier dict or None if invalid
    """
    for tier in config.RANK_TIERS:
        if tier['rank'] == rank_num:
            return tier
    
    return None


def calculate_rank_from_xp(xp: int) -> int:
    """
    Calculate rank number from XP amount
    
    Args:
        xp: Total XP
    
    Returns:
        Rank number (1-6)
    """
    tier = get_rank_tier(xp)
    return tier['rank']


def is_max_rank(rank_num: int) -> bool:
    """
    Check if student is at maximum rank
    
    Args:
        rank_num: Current rank number
    
    Returns:
        True if at max rank
    """
    max_rank = max(tier['rank'] for tier in config.RANK_TIERS)
    return rank_num >= max_rank


def format_student_card(student: Dict[str, Any]) -> str:
    """
    Format a complete student info card
    
    Args:
        student: Student dict
    
    Returns:
        Formatted multi-line string
    """
    rank_display = format_rank_display(student)
    progress = get_rank_progress_bar(student['xp'])
    next_rank = get_next_rank_info(student['xp'])
    
    card = f"👤 {student['display_name']}\n"
    card += f"🏆 {rank_display}\n"
    card += f"✨ XP: {student['xp']}\n"
    card += f"🪙 硬幣: {student['coins']}\n"
    card += f"🔥 連勝: {student['streak']} 日\n"
    
    if next_rank:
        card += f"\n📊 升級進度: {progress}\n"
        card += f"距離 {next_rank['tier']['title_zh']}: {next_rank['xp_needed']} XP"
    else:
        card += f"\n🎊 已達最高級別！"
    
    return card
