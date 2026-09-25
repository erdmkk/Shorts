from __future__ import annotations

from hashlib import sha256
import itertools
import random

from ..config import (DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, PUZZLE_FIT_INTRO_DURATION,
                      PUZZLE_FIT_OUTRO_DURATION, ROUND_DURATIONS, quick_math_average_round, quick_math_thinking,
                      quick_math_tiers)
from ..models import RoundSpec, VideoSpec

OPERATIONS = ("addition", "subtraction", "multiplication")
SYMBOLS = {"addition": "+", "subtraction": "−", "multiplication": "×"}
POSITIONS = ("result", "right", "left")


def allowed_operations(difficulty: str) -> tuple[str, ...]:
    return ("addition", "subtraction") if difficulty == "easy" else OPERATIONS


def allowed_positions(operation: str, difficulty: str) -> tuple[str, ...]:
    if difficulty == "easy" and operation == "subtraction":
        return ("result",)
    return POSITIONS


def _equation(rng: random.Random, operation: str, difficulty: str) -> tuple[int, int, int]:
    if operation == "addition":
        low, high = {"easy": (1, 9), "medium": (4, 30), "hard": (8, 60)}[difficulty]
        a, b = rng.randint(low, high), rng.randint(low, high)
        return a, b, a + b
    if operation == "subtraction":
        low, high = {"easy": (3, 12), "medium": (10, 60), "hard": (20, 99)}[difficulty]
        a = rng.randint(low, high)
        b = rng.randint(1, a - 1)
        return a, b, a - b
    table_high, factor_high = ((5, 10) if difficulty == "medium" else (9, 12))
    a, b = rng.randint(2, table_high), rng.randint(2, factor_high)
    return a, b, a * b


def _operation_schedule(rng: random.Random, difficulty: str, operation: str, count: int) -> list[str]:
    allowed = allowed_operations(difficulty)
    if operation in allowed:
        return [operation] * count
    cycle = ["addition", "addition", "subtraction"] if difficulty == "easy" else list(allowed)
    schedule = [cycle[index % len(cycle)] for index in range(count)]
    rng.shuffle(schedule)
    return schedule


def legacy_generate(seed: int, difficulty: str = "easy", operation: str = "mixed", round_count: int | None = None) -> VideoSpec:
    """V7 single-equation rounds (older videos only; new videos use Shape Equations)."""
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    operation = operation if operation in (*OPERATIONS, "mixed") else "mixed"
    if operation not in allowed_operations(difficulty):
        operation = "mixed"
    count = round_count or 5
    rng = random.Random(f"quick_math_v7:{seed}:{difficulty}:{operation}:{count}")
    schedule = _operation_schedule(rng, difficulty, operation, count)
    rounds: list[RoundSpec] = []
    used: set[tuple[str, int, int, str]] = set()
    used_answers: set[int] = set()
    used_templates: set[str] = set()
    for index, selected in enumerate(schedule):
        positions = allowed_positions(selected, difficulty)
        for attempt in range(200):
            a, b, result = _equation(rng, selected, difficulty)
            position = rng.choice(positions)
            if index == count - 1 and len(used_templates) == 1 and len(positions) > 1:
                alternatives = [item for item in positions if item not in used_templates]
                if alternatives:
                    position = rng.choice(alternatives)
            answer = {"left": a, "right": b, "result": result}[position]
            key = (selected, a, b, position)
            if key in used or (answer in used_answers and attempt < 150):
                continue
            used.add(key)
            used_answers.add(answer)
            used_templates.add(position)
            rounds.append(RoundSpec(index, "quick_math", {
                "a": a, "b": b, "result": result, "operation": selected,
                "symbol": SYMBOLS[selected], "unknown_position": position,
                "equation_template": f"{selected}_{position}",
            }, answer))
            break
        else:
            raise RuntimeError("Could not create a unique equation")
    stable_id = sha256(f"quick_math_v7:{seed}:{difficulty}:{operation}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "quick_math", seed, difficulty, "numbers", tuple(rounds),
                     INTRO_DURATION, ROUND_DURATIONS["quick_math"], OUTRO_DURATION, operation)


# ---------------------------------------------------------------- Shape Equations (current Quick Math format)

FORMATS = ("shapes", "operators")
DEFAULT_FORMAT = "shapes"
SHAPE_POOL = ("triangle", "square", "circle", "star", "heart", "hexagon", "diamond")
SHAPE_COLORS = {"triangle": "#FFD23F", "square": "#3DA9FF", "circle": "#FF4D6D", "star": "#B388FF",
                "heart": "#FF6FB5", "hexagon": "#3DF08F", "diamond": "#FF8A3D"}
OPS = ("+", "−", "×", "÷")
# Level tiers: each later tier adds a shape, multiplication, an order-of-operations trap, then division.
TIERS = (
    {"shapes": 2, "values": (2, 10), "clue_ops": ("+", "−"), "question_ops": ("+", "−"), "terms": 3, "trap": False},
    {"shapes": 3, "values": (2, 12), "clue_ops": ("+", "−", "×"), "question_ops": ("+", "−"), "terms": 3, "trap": False},
    {"shapes": 3, "values": (2, 12), "clue_ops": ("+", "−", "×"), "question_ops": ("+", "−", "×"), "terms": 3, "trap": True},
    {"shapes": 3, "values": (2, 12), "clue_ops": ("+", "−", "×", "÷"), "question_ops": ("+", "−", "×", "÷"), "terms": 4, "trap": True},
)
# Keep the arithmetic doable in your head: the challenge is the logic and the trap, not long multiplication.
MAX_CLUE_RESULT = 150
MAX_ANSWER = 150
MAX_SMALL_FACTOR = 9  # in every product at least one factor is 9 or less (no 11 × 12); squares stay within 12 × 12


def tier_for(index: int, count: int) -> int:
    return quick_math_tiers(count)[index]


def friendly(terms: list, values: dict[str, int]) -> bool:
    """True when every product has a small factor (a square of one shape is always fine)."""
    for position, op in enumerate(terms[1::2]):
        if op == "×":
            left, right = terms[2 * position], terms[2 * position + 2]
            if left != right and min(values[left], values[right]) > MAX_SMALL_FACTOR:
                return False
    return True


def evaluate(terms: list, values: dict[str, int], precedence: bool = True) -> int | None:
    """Evaluate a term list such as ["s0", "+", "s1", "×", "s2"]. Returns None for inexact division."""
    numbers = [values[item] if isinstance(item, str) and item.startswith("s") else item for item in terms[0::2]]
    ops = list(terms[1::2])
    if not precedence:
        total = numbers[0]
        for op, number in zip(ops, numbers[1:]):
            total = _apply(total, op, number)
            if total is None:
                return None
        return total
    # Multiplication and division first, left to right; then addition and subtraction.
    stack, pending = [numbers[0]], []
    for op, number in zip(ops, numbers[1:]):
        if op in ("×", "÷"):
            stack[-1] = _apply(stack[-1], op, number)
            if stack[-1] is None:
                return None
        else:
            pending.append(op); stack.append(number)
    total = stack[0]
    for op, number in zip(pending, stack[1:]):
        total = _apply(total, op, number)
    return total


def _apply(a: int, op: str, b: int) -> int | None:
    if op == "+":
        return a + b
    if op == "−":
        return a - b
    if op == "×":
        return a * b
    if b == 0 or a % b:
        return None
    return a // b


def _first_clue(rng: random.Random, tier: dict, value: int) -> tuple[list, int] | None:
    options = [(["s0", "+", "s0"], 2 * value), (["s0", "+", "s0", "+", "s0"], 3 * value)]
    if "×" in tier["clue_ops"] and value <= 12:
        options.append((["s0", "×", "s0"], value * value))
    return rng.choice(options)


def _next_clue(rng: random.Random, tier: dict, new: str, known: list[str], values: dict[str, int]) -> tuple[list, int] | None:
    k = rng.choice(known)
    options = [[k, "+", new], [new, "+", k], [k, "+", new, "+", new]]
    if values[new] > values[k]:
        options.append([new, "−", k])
    if "×" in tier["clue_ops"]:
        options += [[k, "×", new], [new, "×", k, "−", k]]
    if "÷" in tier["clue_ops"] and values[new] % values[k] == 0 and values[new] > values[k]:
        options.append([new, "÷", k])
    rng.shuffle(options)
    for terms in options:
        result = evaluate(terms, values)
        if result is not None and 0 <= result <= MAX_CLUE_RESULT and friendly(terms, values):
            return terms, result
    return None


def _question(rng: random.Random, tier: dict, names: list[str], values: dict[str, int]) -> tuple[list, int, int] | None:
    for _ in range(80):
        shapes = list(names) + [rng.choice(names) for _ in range(tier["terms"] - len(names))]
        rng.shuffle(shapes)
        ops = [rng.choice(tier["question_ops"]) for _ in range(tier["terms"] - 1)]
        terms: list = [shapes[0]]
        for op, shape in zip(ops, shapes[1:]):
            terms += [op, shape]
        if any(op in ("−", "÷") and first == second for first, op, second in zip(terms[0::2], ops, terms[2::2])):
            continue  # "x − x" and "x ÷ x" are giveaways
        signed = {}
        for position, shape in enumerate(shapes):  # a shape that is both added and subtracted cancels out
            sign = "−" if position and ops[position - 1] == "−" else "+"
            signed.setdefault(shape, set()).add(sign)
        if tier["question_ops"] == ("+", "−") and any(len(signs) > 1 for signs in signed.values()):
            continue
        answer = evaluate(terms, values)
        naive = evaluate(terms, values, precedence=False)
        if answer is None or not 0 <= answer <= MAX_ANSWER or answer in values.values() or not friendly(terms, values):
            continue
        if tier["trap"] and (naive is None or naive == answer or not any(op in ("×", "÷") for op in ops[1:])):
            continue
        return terms, answer, naive if naive is not None else answer
    return None


def _shape_round(rng: random.Random, index: int, tier_index: int, used_answers: set[int], difficulty: str) -> RoundSpec | None:
    tier = TIERS[tier_index]
    shapes = rng.sample(SHAPE_POOL, tier["shapes"])
    low, high = tier["values"]
    raw = rng.sample(range(low, high + 1), tier["shapes"])
    names = [f"s{slot}" for slot in range(tier["shapes"])]
    values = dict(zip(names, raw))
    clues = []
    first = _first_clue(rng, tier, values["s0"])
    if first is None:
        return None
    clues.append({"terms": first[0], "result": first[1]})
    for slot in range(1, tier["shapes"]):
        clue = _next_clue(rng, tier, names[slot], names[:slot], values)
        if clue is None:
            return None
        clues.append({"terms": clue[0], "result": clue[1]})
    if tier_index >= 2 and not any("×" in clue["terms"] or "÷" in clue["terms"] for clue in clues):
        return None
    question = _question(rng, tier, names, values)
    if question is None or question[1] in used_answers:
        return None
    terms, answer, naive = question
    if any(clue["terms"] == terms or clue["result"] == answer for clue in clues):
        return None
    data = {
        "format": "shapes", "operation": "shapes", "equation_template": f"shapes_tier{tier_index}", "tier": tier_index,
        "shapes": [{"name": name, "shape": shape, "color": SHAPE_COLORS[shape], "value": values[name]}
                   for name, shape in zip(names, shapes)],
        "clues": clues, "question": {"terms": terms}, "left_to_right": naive,
        "thinking_seconds": quick_math_thinking(difficulty, tier_index),
        # Trap levels reveal the hardest shape (the one the last clue unlocks) halfway through the timer.
        "hint_shape": names[-1] if tier["trap"] else None,
    }
    return RoundSpec(index, "quick_math", data, answer)


def generate(seed: int, difficulty: str = "hard", operation: str = DEFAULT_FORMAT, round_count: int | None = None) -> VideoSpec:
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "hard"
    fmt = operation if operation in FORMATS else DEFAULT_FORMAT  # the Operation field now carries the format
    count = round_count or DEFAULT_ROUNDS["quick_math"]
    if fmt == "operators":
        return _generate_operators(seed, difficulty, count)
    rng = random.Random(f"quick_math_shapes_v2:{seed}:{difficulty}:{count}")
    rounds: list[RoundSpec] = []
    used_answers: set[int] = set()
    used_sets: set[tuple[str, ...]] = set()
    for index in range(count):
        for _ in range(2000):
            item = _shape_round(rng, index, tier_for(index, count), used_answers, difficulty)
            if item is None:
                continue
            shape_set = tuple(sorted(entry["shape"] for entry in item.data["shapes"]))
            if shape_set in used_sets:
                continue
            used_sets.add(shape_set); used_answers.add(item.answer); rounds.append(item)
            break
        else:
            raise RuntimeError("Could not create a shape equation")
    stable_id = sha256(f"quick_math_shapes_v2:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "quick_math", seed, difficulty, "numbers", tuple(rounds), PUZZLE_FIT_INTRO_DURATION,
                     quick_math_average_round(difficulty, [item.data["tier"] for item in rounds]), PUZZLE_FIT_OUTRO_DURATION, fmt)


def _generate_operators(seed: int, difficulty: str, count: int) -> VideoSpec:
    rng = random.Random(f"quick_math_operators_v1:{seed}:{difficulty}:{count}")
    rounds: list[RoundSpec] = []
    used: set[tuple] = set()
    for index in range(count):
        for _ in range(20000):
            item = _operator_round(rng, index, tier_for(index, count), used, difficulty)
            if item is not None:
                rounds.append(item)
                break
        else:
            raise RuntimeError("Could not create a missing-operator puzzle")
    stable_id = sha256(f"quick_math_operators_v1:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "quick_math", seed, difficulty, "numbers", tuple(rounds), PUZZLE_FIT_INTRO_DURATION,
                     quick_math_average_round(difficulty, [item.data["tier"] for item in rounds]), PUZZLE_FIT_OUTRO_DURATION,
                     "operators")


def shape_errors(data: dict, answer, difficulty: str | None = None) -> list[str]:
    result: list[str] = []
    tier_index = data.get("tier")
    if tier_index not in range(len(TIERS)):
        return ["shape equation tier is invalid"]
    if difficulty is not None and data.get("thinking_seconds") != quick_math_thinking(difficulty, tier_index):
        result.append("shape equation thinking time does not match its level")
    tier = TIERS[tier_index]
    shapes = data.get("shapes", [])
    names = [entry.get("name") for entry in shapes]
    values = {entry.get("name"): entry.get("value") for entry in shapes}
    if (len(shapes) != tier["shapes"] or names != [f"s{slot}" for slot in range(tier["shapes"])]
            or len({entry.get("shape") for entry in shapes}) != len(shapes)
            or any(entry.get("shape") not in SHAPE_POOL or entry.get("color") != SHAPE_COLORS.get(entry.get("shape")) for entry in shapes)):
        return ["shape equation shapes are invalid"]
    low, high = tier["values"]
    if len(set(values.values())) != len(values) or any(not isinstance(v, int) or not low <= v <= high for v in values.values()):
        result.append("shape values must be distinct and inside the tier range")
    clues = data.get("clues", [])
    known: set[str] = set()
    if len(clues) != len(shapes):
        result.append("every shape needs exactly one clue")
    for slot, clue in enumerate(clues):
        terms = clue.get("terms", [])
        used = {item for item in terms[0::2]}
        ops = set(terms[1::2])
        # Each clue introduces exactly one new shape, so the board is solvable step by step with one answer.
        if (used - known != {f"s{slot}"} or not ops <= set(tier["clue_ops"]) or evaluate(terms, values) != clue.get("result")
                or not friendly(terms, values)):
            result.append("shape clue is invalid")
        known |= used
    terms = data.get("question", {}).get("terms", [])
    if set(terms[0::2]) != set(names) or not set(terms[1::2]) <= set(tier["question_ops"]) or len(terms) != tier["terms"] * 2 - 1:
        result.append("shape question is invalid")
    elif evaluate(terms, values) != answer or not isinstance(answer, int) or not 0 <= answer <= MAX_ANSWER:
        result.append("shape answer is incorrect")
    elif tier["trap"] and evaluate(terms, values, precedence=False) == answer:
        result.append("the final levels must hide an order-of-operations trap")
    if data.get("hint_shape") != (names[-1] if tier["trap"] else None):
        result.append("shape hint is invalid")
    return result


# ---------------------------------------------------------------- Missing Operators format

# Level tiers: more slots, division, then an order-of-operations trap.
OPERATOR_TIERS = (
    {"numbers": 3, "ops": ("+", "−", "×"), "values": (2, 12), "trap": False},
    {"numbers": 3, "ops": ("+", "−", "×", "÷"), "values": (2, 12), "trap": False},
    {"numbers": 4, "ops": ("+", "−", "×"), "values": (2, 12), "trap": True},
    {"numbers": 4, "ops": ("+", "−", "×", "÷"), "values": (2, 12), "trap": True},
)
MAX_TARGET = 150


def _with_ops(numbers: list[int], ops: tuple[str, ...]) -> list:
    terms: list = [numbers[0]]
    for op, number in zip(ops, numbers[1:]):
        terms += [op, number]
    return terms


def _friendly_numbers(terms: list) -> bool:
    return all(not (op == "×" and min(terms[2 * position], terms[2 * position + 2]) > MAX_SMALL_FACTOR)
               for position, op in enumerate(terms[1::2]))


def operator_solutions(numbers: list[int], allowed: tuple[str, ...], target: int) -> list[tuple[str, ...]]:
    """Every sign combination that reaches the target (× and ÷ first; division must be exact)."""
    return [ops for ops in itertools.product(allowed, repeat=len(numbers) - 1)
            if evaluate(_with_ops(numbers, ops), {}) == target]


def _operator_round(rng: random.Random, index: int, tier_index: int, used: set[tuple], difficulty: str) -> RoundSpec | None:
    tier = OPERATOR_TIERS[tier_index]
    low, high = tier["values"]
    numbers = [rng.randint(low, high) for _ in range(tier["numbers"])]
    ops = tuple(rng.choice(tier["ops"]) for _ in range(tier["numbers"] - 1))
    if tier_index >= 1 and not any(op in ("×", "÷") for op in ops):
        return None
    if len(set(ops)) == 1 and len(ops) > 1:
        return None  # "+ + +" is too easy to guess
    if tier_index == len(OPERATOR_TIERS) - 1 and "÷" not in ops:
        return None  # the final level always needs a division
    if any(op == "÷" and numbers[position] == numbers[position + 1] for position, op in enumerate(ops)):
        return None  # "9 ÷ 9" just adds confusion
    terms = _with_ops(numbers, ops)
    target = evaluate(terms, {})
    if target is None or not 0 <= target <= MAX_TARGET or not _friendly_numbers(terms):
        return None
    if operator_solutions(numbers, tier["ops"], target) != [ops]:
        return None  # exactly one combination works
    naive = evaluate(terms, {}, precedence=False)
    if tier["trap"] and (naive is None or naive == target or not any(op in ("×", "÷") for op in ops[1:])):
        return None
    key = (tuple(numbers), target)
    if key in used:
        return None
    used.add(key)
    data = {"format": "operators", "operation": "operators", "equation_template": f"operators_tier{tier_index}",
            "tier": tier_index, "numbers": numbers, "allowed_ops": list(tier["ops"]), "target": target,
            "operators": list(ops), "left_to_right": naive if naive is not None else target,
            "thinking_seconds": quick_math_thinking(difficulty, tier_index), "hint_slot": operator_hint(ops, tier)}
    return RoundSpec(index, "quick_math", data, "".join(ops))


def operator_hint(ops: tuple[str, ...], tier: dict) -> int | None:
    """Trap levels reveal the first × or ÷ halfway through the timer: it shows where the order of operations bites."""
    if not tier["trap"]:
        return None
    return next((position for position, op in enumerate(ops) if op in ("×", "÷")), None)


def operator_errors(data: dict, answer, difficulty: str | None = None) -> list[str]:
    tier_index = data.get("tier")
    if tier_index not in range(len(OPERATOR_TIERS)):
        return ["missing-operator tier is invalid"]
    tier = OPERATOR_TIERS[tier_index]
    result: list[str] = []
    numbers, ops, target = data.get("numbers", []), tuple(data.get("operators", [])), data.get("target")
    low, high = tier["values"]
    if len(numbers) != tier["numbers"] or any(not isinstance(n, int) or not low <= n <= high for n in numbers):
        return ["missing-operator numbers are invalid"]
    if data.get("allowed_ops") != list(tier["ops"]) or len(ops) != len(numbers) - 1 or not set(ops) <= set(tier["ops"]):
        return ["missing-operator signs are invalid"]
    if difficulty is not None and data.get("thinking_seconds") != quick_math_thinking(difficulty, tier_index):
        result.append("missing-operator thinking time does not match its level")
    if evaluate(_with_ops(numbers, ops), {}) != target or answer != "".join(ops):
        result.append("missing-operator answer is incorrect")
    elif operator_solutions(numbers, tier["ops"], target) != [ops]:
        result.append("missing-operator puzzle must have exactly one solution")
    elif tier["trap"] and evaluate(_with_ops(numbers, ops), {}, precedence=False) == target:
        result.append("the final levels must hide an order-of-operations trap")
    if any(op == "÷" and numbers[position] == numbers[position + 1] for position, op in enumerate(ops)):
        result.append("missing-operator puzzles never divide a number by itself")
    if data.get("hint_slot") != operator_hint(ops, tier):
        result.append("missing-operator hint is invalid")
    return result
