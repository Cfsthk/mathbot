"""
Twist/modifier system for gauntlet challenges
Adds special rules and conditions to make challenges more interesting
"""
from typing import Dict, Any, List, Optional


# Twist definitions with Cantonese names and effects
TWISTS = [
    {
        'id': 1,
        'name_zh': '限時90秒',
        'description_zh': '必須在90秒內回答',
        'required_rank': 3,
        'effect_key': 'time_limit_90'
    },
    {
        'id': 2,
        'name_zh': '答案須為偶數',
        'description_zh': '答案必須是偶數才算正確',
        'required_rank': 3,
        'effect_key': 'even_only'
    },
    {
        'id': 3,
        'name_zh': '答案四捨五入至十位',
        'description_zh': '答案須四捨五入至最接近的十位數',
        'required_rank': 3,
        'effect_key': 'round_to_ten'
    },
    {
        'id': 4,
        'name_zh': '雙倍或全輸',
        'description_zh': '贏了得雙倍硬幣，輸了失去一半硬幣',
        'required_rank': 4,
        'effect_key': 'double_or_nothing'
    },
    {
        'id': 5,
        'name_zh': '不可用乘法',
        'description_zh': '題目不會包含乘法運算（顯示警告）',
        'required_rank': 4,
        'effect_key': 'no_multiplication'
    },
    {
        'id': 6,
        'name_zh': '限時60秒',
        'description_zh': '必須在60秒內回答（更嚴格）',
        'required_rank': 5,
        'effect_key': 'time_limit_60'
    }
]


def get_available_twists(rank_num: int) -> List[Dict[str, Any]]:
    """
    Get twists available for a given rank
    
    Args:
        rank_num: Student's rank number (1-6)
    
    Returns:
        List of twist dicts
    """
    return [twist for twist in TWISTS if twist['required_rank'] <= rank_num]


def get_twist_by_id(twist_id: int) -> Optional[Dict[str, Any]]:
    """
    Get twist by ID
    
    Args:
        twist_id: Twist ID
    
    Returns:
        Twist dict or None
    """
    for twist in TWISTS:
        if twist['id'] == twist_id:
            return twist
    
    return None


def apply_twist_effect(twist_id: Optional[int], answer: float, 
                       time_taken_seconds: int, coins_stake: int) -> Dict[str, Any]:
    """
    Apply twist effect and validate answer/conditions
    
    Args:
        twist_id: Twist ID (or None for no twist)
        answer: The numeric answer
        time_taken_seconds: Time taken to answer
        coins_stake: Coins at stake in the challenge
    
    Returns:
        Dict with:
        - valid: bool (whether answer meets twist conditions)
        - reason: str (explanation if invalid)
        - coins_modifier: float (multiplier for coins, e.g., 2.0 for double)
    """
    if twist_id is None:
        return {
            'valid': True,
            'reason': '',
            'coins_modifier': 1.0
        }
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return {
            'valid': True,
            'reason': '',
            'coins_modifier': 1.0
        }
    
    effect_key = twist['effect_key']
    
    # Time limit effects
    if effect_key == 'time_limit_90':
        if time_taken_seconds > 90:
            return {
                'valid': False,
                'reason': '超過90秒時限',
                'coins_modifier': 1.0
            }
    
    elif effect_key == 'time_limit_60':
        if time_taken_seconds > 60:
            return {
                'valid': False,
                'reason': '超過60秒時限',
                'coins_modifier': 1.0
            }
    
    # Answer validation effects
    elif effect_key == 'even_only':
        if int(answer) % 2 != 0:
            return {
                'valid': False,
                'reason': '答案不是偶數',
                'coins_modifier': 1.0
            }
    
    elif effect_key == 'round_to_ten':
        # Check if answer is rounded to nearest 10
        rounded = round(answer / 10) * 10
        if abs(answer - rounded) > 0.01:  # Small tolerance for floating point
            return {
                'valid': False,
                'reason': '答案未四捨五入至十位',
                'coins_modifier': 1.0
            }
    
    # Coin modifier effects
    elif effect_key == 'double_or_nothing':
        # This is resolved after knowing win/lose
        # Winner gets 2x coins, loser loses coins
        return {
            'valid': True,
            'reason': '',
            'coins_modifier': 2.0
        }
    
    # Default: valid
    return {
        'valid': True,
        'reason': '',
        'coins_modifier': 1.0
    }


def format_twist_display(twist_id: Optional[int]) -> str:
    """
    Format twist for display in challenge setup
    
    Args:
        twist_id: Twist ID or None
    
    Returns:
        Formatted string in Cantonese
    """
    if twist_id is None:
        return '無特殊規則'
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return '無特殊規則'
    
    return f"⚡ {twist['name_zh']}\n{twist['description_zh']}"


def get_twist_warning(twist_id: Optional[int]) -> str:
    """
    Get warning message to show before challenge starts
    
    Args:
        twist_id: Twist ID or None
    
    Returns:
        Warning string (empty if no warning needed)
    """
    if twist_id is None:
        return ''
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return ''
    
    effect_key = twist['effect_key']
    
    warnings = {
        'time_limit_90': '⏱️ 注意：每題只有90秒作答時間！',
        'time_limit_60': '⏱️ 注意：每題只有60秒作答時間！',
        'even_only': '🔢 注意：答案必須是偶數！',
        'round_to_ten': '🔢 注意：答案須四捨五入至十位！',
        'double_or_nothing': '💰 注意：贏了得雙倍硬幣，輸了失去一半硬幣！',
        'no_multiplication': '📝 注意：題目已排除乘法運算'
    }
    
    return warnings.get(effect_key, '')


def calculate_twist_coin_penalty(twist_id: Optional[int], loser_current_coins: int) -> int:
    """
    Calculate coin penalty for loser when twist has coin effects
    
    Args:
        twist_id: Twist ID
        loser_current_coins: Loser's current coin balance
    
    Returns:
        Coins to deduct (negative number)
    """
    if twist_id is None:
        return 0
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return 0
    
    if twist['effect_key'] == 'double_or_nothing':
        # Loser loses half their coins (capped at reasonable amount)
        penalty = min(loser_current_coins // 2, 50)
        return -penalty
    
    return 0


def is_twist_unlocked(twist_id: int, student_rank: int) -> bool:
    """
    Check if a twist is unlocked for a student's rank
    
    Args:
        twist_id: Twist ID
        student_rank: Student's rank number
    
    Returns:
        True if unlocked
    """
    twist = get_twist_by_id(twist_id)
    if not twist:
        return False
    
    return student_rank >= twist['required_rank']


def format_twist_menu(rank_num: int) -> str:
    """
    Format available twists as a menu
    
    Args:
        rank_num: Student's rank number
    
    Returns:
        Formatted menu string
    """
    available = get_available_twists(rank_num)
    
    if not available:
        return '你未解鎖任何特殊規則。\n繼續升級即可解鎖！'
    
    menu = '選擇特殊規則：\n\n'
    for twist in available:
        menu += f"{twist['id']}. {twist['name_zh']}\n"
        menu += f"   {twist['description_zh']}\n\n"
    
    menu += '0. 無特殊規則'
    
    return menu


def validate_twist_for_question(twist_id: Optional[int], question: Dict[str, Any]) -> bool:
    """
    Check if a twist is compatible with a question
    (e.g., 'no_multiplication' twist shouldn't be used with multiplication questions)
    
    Args:
        twist_id: Twist ID
        question: Question dict
    
    Returns:
        True if compatible
    """
    if twist_id is None:
        return True
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return True
    
    # Check for incompatible combinations
    if twist['effect_key'] == 'no_multiplication':
        # Check if question formula contains multiplication
        formula = question.get('answer_formula', '')
        if '*' in formula:
            return False
    
    return True


def get_twist_time_limit(twist_id: Optional[int]) -> Optional[int]:
    """
    Get time limit in seconds if twist imposes one
    
    Args:
        twist_id: Twist ID
    
    Returns:
        Time limit in seconds, or None if no limit
    """
    if twist_id is None:
        return None
    
    twist = get_twist_by_id(twist_id)
    if not twist:
        return None
    
    time_limits = {
        'time_limit_90': 90,
        'time_limit_60': 60
    }
    
    return time_limits.get(twist['effect_key'])
