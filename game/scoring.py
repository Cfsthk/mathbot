"""
Scoring calculation module
Handles XP/coin rewards, multipliers, streak bonuses, and challenge resolution
"""
from typing import Dict, Any
import asyncpg
import config
import database as db
from game import ranks


def compute_rank_gap(challenger_rank_pos: int, defender_rank_pos: int) -> str:
    """
    Determine rank gap category between challenger and defender
    
    Args:
        challenger_rank_pos: Challenger's rank position (1=highest)
        defender_rank_pos: Defender's rank position (1=highest)
    
    Returns:
        Gap category key: 'higher_3plus', 'higher_1_2', 'same', 'lower'
    """
    gap = challenger_rank_pos - defender_rank_pos
    
    if gap >= 3:
        # Challenger is 3+ positions lower (challenging upward)
        return 'higher_3plus'
    elif gap >= 1:
        # Challenger is 1-2 positions lower
        return 'higher_1_2'
    elif gap >= -2:
        # Similar rank (within 2 positions)
        return 'same'
    else:
        # Challenger is higher ranked (challenging downward)
        return 'lower'


def compute_xp_reward(base_xp: int, difficulty: int, rank_gap_key: str, streak: int = 0) -> int:
    """
    Calculate XP reward with all multipliers applied
    
    Args:
        base_xp: Base XP amount
        difficulty: Question difficulty (1-5)
        rank_gap_key: Rank gap category
        streak: Current streak days (for bonus calculation)
    
    Returns:
        Final XP reward (integer)
    """
    # Apply difficulty multiplier
    xp = base_xp * config.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    
    # Apply rank gap multiplier
    xp = xp * config.RANK_GAP_MULTIPLIERS.get(rank_gap_key, 1.0)
    
    # Apply streak bonus if applicable
    if streak > 0:
        xp = apply_streak_bonus(int(xp), streak)
    
    return int(xp)


def compute_coins_reward(base_coins: int, difficulty: int, rank_gap_key: str) -> int:
    """
    Calculate coin reward with multipliers applied
    
    Args:
        base_coins: Base coin amount
        difficulty: Question difficulty (1-5)
        rank_gap_key: Rank gap category
    
    Returns:
        Final coin reward (integer)
    """
    # Apply difficulty multiplier
    coins = base_coins * config.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    
    # Apply rank gap multiplier
    coins = coins * config.RANK_GAP_MULTIPLIERS.get(rank_gap_key, 1.0)
    
    return int(coins)


def apply_streak_bonus(xp: int, streak_days: int) -> int:
    """
    Apply streak bonus to XP
    
    Args:
        xp: Base XP amount
        streak_days: Current streak count
    
    Returns:
        XP with streak bonus applied
    """
    # Find highest applicable streak bonus
    bonus_percent = 0
    for streak_threshold in sorted(config.STREAK_BONUSES.keys(), reverse=True):
        if streak_days >= streak_threshold:
            bonus_percent = config.STREAK_BONUSES[streak_threshold]['xp_bonus_percent']
            break
    
    if bonus_percent > 0:
        return int(xp * (1 + bonus_percent / 100))
    
    return xp


def get_streak_bonus_coins(streak_days: int) -> int:
    """
    Get bonus coins for streak milestone
    
    Args:
        streak_days: Current streak count
    
    Returns:
        Bonus coins amount
    """
    for streak_threshold in sorted(config.STREAK_BONUSES.keys(), reverse=True):
        if streak_days >= streak_threshold:
            return config.STREAK_BONUSES[streak_threshold].get('coins_bonus', 0)
    
    return 0


async def resolve_challenge_outcome(pool: asyncpg.Pool, challenge_id: int, 
                                    winner: str) -> Dict[str, Any]:
    """
    Resolve challenge outcome and award XP/coins to both players
    
    Args:
        pool: Database connection pool
        challenge_id: Challenge ID
        winner: 'challenger', 'defender', or 'timeout'
    
    Returns:
        Summary dict with rewards and rank changes
    """
    # Get challenge details
    challenge = await db.get_challenge_by_id(pool, challenge_id)
    if not challenge:
        return {}
    
    challenger_id = challenge['challenger_id']
    defender_id = challenge['defender_id']
    
    # Get both students
    challenger = await db.get_student_by_id(pool, challenger_id)
    defender = await db.get_student_by_id(pool, defender_id)
    
    if not challenger or not defender:
        return {}
    
    # Get challenge questions to determine difficulty
    questions = await db.get_challenge_questions(pool, challenge_id)
    avg_difficulty = 2  # Default
    if questions:
        difficulties = []
        for cq in questions:
            q = await db.get_question_by_id(pool, cq['question_id'])
            if q:
                difficulties.append(q['difficulty'])
        if difficulties:
            avg_difficulty = int(sum(difficulties) / len(difficulties))
    
    # Calculate rank gap
    challenger_pos = await db.get_student_rank_position(pool, challenger_id, challenger['grade'])
    defender_pos = await db.get_student_rank_position(pool, defender_id, defender['grade'])
    rank_gap = compute_rank_gap(challenger_pos, defender_pos)
    
    # Initialize rewards
    xp_challenger = 0
    xp_defender = 0
    coins_challenger = 0
    coins_defender = 0
    
    if winner == 'challenger':
        # Challenger won all 3 questions
        xp_challenger = compute_xp_reward(
            config.XP_CHALLENGE_WIN_BASE, 
            avg_difficulty, 
            rank_gap,
            challenger['streak']
        )
        coins_challenger = compute_coins_reward(
            config.COINS_CHALLENGE_WIN_BASE,
            avg_difficulty,
            rank_gap
        )
        
        # Defender gets consolation XP only
        xp_defender = config.XP_CHALLENGE_LOSE_CONSOLATION
        
    elif winner == 'defender':
        # Defender successfully answered all 3 questions
        xp_defender = compute_xp_reward(
            config.XP_DEFEND_WIN_BASE,
            avg_difficulty,
            rank_gap,
            defender['streak']
        )
        coins_defender = compute_coins_reward(
            config.COINS_DEFEND_WIN_BASE,
            avg_difficulty,
            rank_gap
        )
        
        # Challenger gets consolation XP
        xp_challenger = config.XP_CHALLENGE_LOSE_CONSOLATION
        
    elif winner == 'timeout':
        # Defender didn't respond in time, challenger wins
        xp_challenger = config.XP_TIMEOUT_WIN
        coins_challenger = int(config.COINS_CHALLENGE_WIN_BASE * 0.5)  # Half coins
        xp_defender = 0  # No consolation for timeout
    
    # Award XP and coins
    await db.update_student_xp_coins(pool, challenger_id, xp_challenger, coins_challenger)
    await db.update_student_xp_coins(pool, defender_id, xp_defender, coins_defender)
    
    # Check for rank ups
    challenger_rank_up = await db.check_and_update_rank(pool, challenger_id)
    defender_rank_up = await db.check_and_update_rank(pool, defender_id)
    
    # Check for badges
    await check_challenge_badges(pool, challenge_id, winner, challenger_pos, defender_pos)
    
    # Mark challenge as completed
    await db.complete_challenge(
        pool, challenge_id, winner,
        xp_challenger, xp_defender,
        coins_challenger, coins_defender
    )
    
    return {
        'winner': winner,
        'challenger': {
            'id': challenger_id,
            'name': challenger['display_name'],
            'xp': xp_challenger,
            'coins': coins_challenger,
            'rank_up': challenger_rank_up
        },
        'defender': {
            'id': defender_id,
            'name': defender['display_name'],
            'xp': xp_defender,
            'coins': coins_defender,
            'rank_up': defender_rank_up
        }
    }


async def resolve_gauntlet_partial(pool: asyncpg.Pool, challenge_id: int, 
                                   correct_count_defender: int) -> Dict[str, Any]:
    """
    Award partial coins to defender even if they lost
    (Encourages participation and rewards partial success)
    
    Args:
        pool: Database connection pool
        challenge_id: Challenge ID
        correct_count_defender: Number of questions defender got correct
    
    Returns:
        Partial reward summary
    """
    if correct_count_defender <= 0:
        return {}
    
    challenge = await db.get_challenge_by_id(pool, challenge_id)
    if not challenge:
        return {}
    
    defender_id = challenge['defender_id']
    
    # Award partial coins
    partial_coins = config.COINS_PARTIAL_CORRECT * correct_count_defender
    await db.update_student_xp_coins(pool, defender_id, 0, partial_coins)
    
    return {
        'defender_id': defender_id,
        'partial_coins': partial_coins,
        'questions_correct': correct_count_defender
    }


async def check_challenge_badges(pool: asyncpg.Pool, challenge_id: int, 
                                winner: str, challenger_pos: int, 
                                defender_pos: int) -> None:
    """
    Check and award badges based on challenge outcome
    
    Args:
        pool: Database connection pool
        challenge_id: Challenge ID
        winner: 'challenger' or 'defender'
        challenger_pos: Challenger's rank position
        defender_pos: Defender's rank position
    """
    challenge = await db.get_challenge_by_id(pool, challenge_id)
    if not challenge:
        return
    
    challenger_id = challenge['challenger_id']
    defender_id = challenge['defender_id']
    
    # Giant Killer: Defeat someone 5+ ranks higher
    if winner == 'challenger' and (challenger_pos - defender_pos) >= 5:
        await db.award_badge(pool, challenger_id, 'giant_killer')
    
    if winner == 'defender' and (defender_pos - challenger_pos) >= 5:
        await db.award_badge(pool, defender_id, 'giant_killer')
    
    # Check Undefeated: 5 consecutive successful defenses
    if winner == 'defender':
        await check_undefeated_badge(pool, defender_id)
    
    # Chain Breaker: Answer all 3 questions correctly (4+ is for future expansion)
    if winner == 'defender':
        questions = await db.get_challenge_questions(pool, challenge_id)
        correct_count = sum(1 for q in questions if q.get('answered_correctly'))
        if correct_count >= 3:
            await db.award_badge(pool, defender_id, 'chain_breaker')


async def check_undefeated_badge(pool: asyncpg.Pool, defender_id: int) -> None:
    """
    Check if defender has won 5 consecutive defenses
    Awards 'undefeated' badge if so
    """
    async with pool.acquire() as conn:
        # Get last 5 completed challenges where student was defender
        rows = await conn.fetch(
            """
            SELECT winner FROM challenges
            WHERE defender_id = $1
            AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 5
            """,
            defender_id
        )
        
        if len(rows) >= 5:
            # Check if all 5 were defensive wins
            all_wins = all(row['winner'] == 'defender' for row in rows)
            if all_wins:
                await db.award_badge(pool, defender_id, 'undefeated')


def calculate_daily_rewards(difficulty: int, streak: int) -> Dict[str, int]:
    """
    Calculate daily question rewards
    
    Args:
        difficulty: Question difficulty
        streak: Current streak days
    
    Returns:
        Dict with 'xp' and 'coins' keys
    """
    base_xp = config.XP_DAILY_CORRECT
    base_coins = config.COINS_DAILY_CORRECT
    
    # Apply difficulty multiplier
    xp = int(base_xp * config.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0))
    coins = int(base_coins * config.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0))
    
    # Apply streak bonus to XP
    xp = apply_streak_bonus(xp, streak)
    
    # Add streak milestone bonus coins
    bonus_coins = get_streak_bonus_coins(streak)
    coins += bonus_coins
    
    return {'xp': xp, 'coins': coins}
