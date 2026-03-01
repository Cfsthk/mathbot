"""
Question generation and management module
Handles parameter generation, rendering, answer computation, and MCQ creation
"""
import random
import json
from typing import Dict, Any, List, Tuple, Optional
import asyncpg
import database as db
import config


def generate_question_params(question: Dict[str, Any]) -> Dict[str, int]:
    """
    Generate random parameter values within the question's param_ranges
    
    Args:
        question: Question dict with param_ranges as JSONB/dict
    
    Returns:
        Dict of parameter names to random values
    """
    params = {}
    param_ranges = question['param_ranges']
    
    # Handle both dict and string (from JSONB)
    if isinstance(param_ranges, str):
        param_ranges = json.loads(param_ranges)
    
    for param_name, value_range in param_ranges.items():
        min_val, max_val = value_range
        params[param_name] = random.randint(min_val, max_val)
    
    return params


def render_question(question: Dict[str, Any], params: Dict[str, int]) -> str:
    """
    Substitute parameters into question template
    
    Args:
        question: Question dict with question_template
        params: Parameter values to substitute
    
    Returns:
        Rendered question text in Cantonese
    """
    template = question['question_template']
    
    # Replace each {param} with its value
    rendered = template
    for param_name, value in params.items():
        rendered = rendered.replace(f"{{{param_name}}}", str(value))
    
    return rendered


def compute_answer(formula: str, params: Dict[str, int]) -> float:
    """
    Safely evaluate a formula with given parameters
    
    Args:
        formula: Python-evaluable formula string (e.g. "{A}*{B}/{C}")
        params: Parameter values
    
    Returns:
        Computed numeric answer
    """
    # Substitute parameters into formula
    formula_str = formula
    for param_name, value in params.items():
        formula_str = formula_str.replace(f"{{{param_name}}}", str(value))
    
    # Safe evaluation (only arithmetic operations)
    try:
        # Use eval with restricted namespace for safety
        result = eval(formula_str, {"__builtins__": {}}, {})
        return float(result)
    except Exception as e:
        print(f"Error computing answer: {formula_str} -> {e}")
        return 0.0


def generate_mcq_options(question: Dict[str, Any], params: Dict[str, int]) -> Tuple[List[str], int]:
    """
    Generate 4 MCQ options from option_formulas and shuffle them
    
    Args:
        question: Question dict with option_formulas and correct_option_index
        params: Parameter values
    
    Returns:
        Tuple of (shuffled_options_list, new_correct_index)
    """
    option_formulas = question['option_formulas']
    original_correct_index = question['correct_option_index']
    
    # Compute all option values
    options = []
    for formula in option_formulas:
        value = compute_answer(formula, params)
        # Format nicely (remove .0 for whole numbers)
        if value == int(value):
            options.append(str(int(value)))
        else:
            options.append(f"{value:.2f}".rstrip('0').rstrip('.'))
    
    # Track which option is correct before shuffling
    correct_value = options[original_correct_index]
    
    # Shuffle options
    shuffled_options = options.copy()
    random.shuffle(shuffled_options)
    
    # Find new index of correct answer
    new_correct_index = shuffled_options.index(correct_value)
    
    return shuffled_options, new_correct_index


async def get_gauntlet_questions(pool: asyncpg.Pool, grade: str, 
                                 difficulty_base: int) -> List[Dict[str, Any]]:
    """
    Select 3 questions for a gauntlet challenge with escalating difficulty
    
    Args:
        pool: Database connection pool
        grade: Student grade (P5 or P6)
        difficulty_base: Base difficulty (1-5)
    
    Returns:
        List of 3 question dicts with generated params and options
    """
    questions = []
    
    # Generate 3 questions with increasing difficulty
    difficulties = [
        difficulty_base,
        min(difficulty_base + 1, 5),
        min(difficulty_base + 2, 5)
    ]
    
    for i, diff in enumerate(difficulties):
        # Get random question at this difficulty
        question = await db.get_random_question(pool, diff, grade)
        
        if not question:
            # Fallback: try difficulty 1 if no questions available
            question = await db.get_random_question(pool, 1, grade)
        
        if question:
            # Generate parameters and options
            params = generate_question_params(question)
            options, correct_index = generate_mcq_options(question, params)
            
            # Add generated data to question dict
            question['generated_params'] = params
            question['generated_options'] = options
            question['generated_correct_index'] = correct_index
            question['gauntlet_order'] = i + 1
            
            questions.append(question)
    
    return questions


async def select_daily_question(pool: asyncpg.Pool, student_id: int, 
                                grade: str) -> Optional[Dict[str, Any]]:
    """
    Select an appropriate daily question based on student's progress
    Tries to pick questions not recently seen by the student
    
    Args:
        pool: Database connection pool
        student_id: Student ID
        grade: Student grade
    
    Returns:
        Question dict with generated params and options, or None
    """
    # Get student to determine appropriate difficulty
    student = await db.get_student_by_id(pool, student_id)
    if not student:
        return None
    
    # Determine difficulty based on rank (higher rank = harder questions)
    rank_num = student['rank_num']
    if rank_num <= 2:
        difficulty = 1
    elif rank_num <= 4:
        difficulty = 2
    else:
        difficulty = 3
    
    # Try to get a question at this difficulty
    question = await db.get_random_question(pool, difficulty, grade)
    
    # Fallback to easier question if none available
    if not question:
        question = await db.get_random_question(pool, 1, grade)
    
    if not question:
        return None
    
    # Generate parameters and options
    params = generate_question_params(question)
    options, correct_index = generate_mcq_options(question, params)
    
    question['generated_params'] = params
    question['generated_options'] = options
    question['generated_correct_index'] = correct_index
    
    return question


def validate_answer(selected_option: int, correct_index: int) -> bool:
    """
    Check if selected option matches correct answer
    
    Args:
        selected_option: Index selected by user (0-3)
        correct_index: Correct option index (0-3)
    
    Returns:
        True if correct, False otherwise
    """
    return selected_option == correct_index


async def get_question_difficulty_range(pool: asyncpg.Pool, grade: str) -> Dict[str, int]:
    """
    Get available difficulty range for a grade
    
    Returns:
        Dict with min_difficulty and max_difficulty
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MIN(q.difficulty) as min_diff, MAX(q.difficulty) as max_diff
            FROM questions q
            JOIN topics t ON q.topic_id = t.id
            WHERE q.is_active = TRUE
            AND t.is_active = TRUE
            AND (t.grade = $1 OR t.grade = 'BOTH')
            """,
            grade
        )
        
        if row and row['min_diff'] is not None:
            return {
                'min_difficulty': row['min_diff'],
                'max_difficulty': row['max_diff']
            }
        else:
            return {'min_difficulty': 1, 'max_difficulty': 1}
