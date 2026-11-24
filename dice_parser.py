"""Find dice expressions in chat text and parse a restricted arithmetic grammar."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import math
import operator
import re


DICE_SIDES = (4, 6, 8, 10, 12, 20, 100)
MAX_EXPRESSION_LENGTH = 33_000
MAX_DICE_PER_EXPRESSION = 33_000
MAX_FORMULAS = 5
MAX_MAGNITUDE = 10**100
MAX_EXPONENT = 100
DESCRIPTION_SEPARATOR = " — "
LIST_MARKER = re.compile(r"^[ \t]*[0-9]+([.)])[ \t]+")

KEEP_NOTATION = r"([kK][hHlL])([0-9]+)?"
TOKEN_RE = re.compile(
    r"(?P<dice>[0-9]*[dDкК][0-9]+\w*)"
    r"|(?P<number>[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"|(?P<operator>\*\*|//|[+*/()-])"
    r"|(?P<word>\w+)"
    r"|(?P<invalid>!=|[%^=&|~<>\[\]{}\\@$×÷−·⋅])"
    r"|(?P<separator>[!?]+|\S)"
)
DICE_RE = re.compile(rf"([0-9]*)[dDкК]([0-9]+)(?:{KEEP_NOTATION})?")
KEEP_RE = re.compile(KEEP_NOTATION)

PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2, "//": 2, "**": 4}
UNARY_PRECEDENCE = 3
UNARY_OPERATORS = {"u+": operator.pos, "u-": operator.neg}
OPERATOR_PRECEDENCE = PRECEDENCE | dict.fromkeys(UNARY_OPERATORS, UNARY_PRECEDENCE)
OPERATIONS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
}


class FormulaError(ValueError):
    """A user-facing mistake or limit in a dice expression."""


@dataclass(frozen=True)
class Formula:
    text: str
    description: str = ""


@dataclass(frozen=True)
class Number:
    value: int | float


@dataclass(frozen=True)
class Dice:
    sides: int
    count: int
    keep: str | None
    kept: int


Instruction = Number | Dice | str


def _formula_spans(text: str) -> Iterator[tuple[int, int]]:
    tokens = list(TOKEN_RE.finditer(text))
    parentheses = []
    start = end = 0
    has_dice = False
    for index, token in enumerate(tokens):
        kind = token.lastgroup
        if token.group() == "(":
            previous = tokens[index - 1] if index else None
            attached = previous is not None and previous.lastgroup == "dice" and previous.end() == token.start()
            prose = not attached and index + 1 < len(tokens) and tokens[index + 1].lastgroup == "word"
            parentheses.append(prose)
            if prose:
                kind = "separator"
        elif token.group() == ")" and parentheses and parentheses.pop():
            kind = "separator"
        elif kind == "separator" and token.group()[0] in "!?" and start != end:
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            if following is not None and (
                following.group() in PRECEDENCE
                or (following.start() == token.end() and following.lastgroup in {"dice", "number", "operator"})
            ):
                kind = "invalid"
        if kind == "separator" or (kind == "word" and token.start() != end):
            if has_dice:
                yield start, end
            start = end = token.end()
            has_dice = False
            continue

        if start == end:
            if kind == "word":
                start = end = token.end()
                continue
            start = token.start()
        end = token.end()
        has_dice = has_dice or kind == "dice"

    if has_dice:
        yield start, end


def find_formulas(text: str) -> list[Formula]:
    formulas = []
    for line in text.splitlines():
        marker = LIST_MARKER.match(line)
        if marker:
            rest = line[marker.end():]
            # A decimal literal followed by an operator is part of the expression.
            if marker[1] == ")" or not rest.startswith(("+", "-", "*", "/")):
                line = rest
        segments = line.split(DESCRIPTION_SEPARATOR)
        for index, segment in enumerate(segments):
            for start, end in _formula_spans(segment):
                description = ""
                if index < len(segments) - 1 and end == len(segment.rstrip()):
                    description = DESCRIPTION_SEPARATOR.join(segments[index + 1:]).strip()
                    formulas.append(Formula(segment[start:end], description))
                    break
                formulas.append(Formula(segment[start:end]))
                if len(formulas) > MAX_FORMULAS:
                    return formulas
            else:
                continue
            break
        if len(formulas) > MAX_FORMULAS:
            return formulas
    return formulas


def check_number(value: int | float) -> int | float:
    limit = float(MAX_MAGNITUDE) if isinstance(value, float) else MAX_MAGNITUDE
    if not abs(value) <= limit:
        raise FormulaError("Слишком большое число.")
    return value


def _power(base: int | float, exponent: int | float) -> int | float:
    if abs(exponent) > MAX_EXPONENT:
        raise FormulaError(f"Показатель степени по модулю должен быть не больше {MAX_EXPONENT}.")

    if isinstance(base, int) and isinstance(exponent, int) and exponent >= 0:
        result = 1
        magnitude = abs(base)
        for _ in range(exponent):
            if magnitude and abs(result) > MAX_MAGNITUDE // magnitude:
                raise FormulaError("Слишком большое число.")
            result *= base
        return result

    if base < 0 and exponent % 1:
        raise FormulaError("Степень даёт комплексное число.")
    if base and exponent * math.log(abs(base)) > math.log(MAX_MAGNITUDE):
        raise FormulaError("Слишком большое число.")
    return base**exponent


def calculate(symbol: str, left: int | float, right: int | float) -> int | float:
    try:
        result = _power(left, right) if symbol == "**" else OPERATIONS[symbol](left, right)
    except ZeroDivisionError:
        raise FormulaError("Деление на ноль.") from None
    except OverflowError:
        raise FormulaError("Слишком большое число.") from None
    return check_number(result)


def _bounded_int(text: str, limit: int, error: str) -> int:
    digits = text.lstrip("0") or "0"
    maximum = str(limit)
    if len(digits) > len(maximum) or (len(digits) == len(maximum) and digits > maximum):
        raise FormulaError(error)
    return int(digits)


def _plain_token(token: re.Match[str]) -> Number | str:
    text = token.group()
    if token.lastgroup != "number":
        return text
    if "." in text:
        return Number(check_number(float(text)))
    return Number(_bounded_int(text, MAX_MAGNITUDE, "Слишком большое число."))


def _compile(tokens: Iterable[Instruction]) -> list[Instruction]:
    """Convert infix tokens to postfix instructions using an operator stack."""
    instructions: list[Instruction] = []
    operators: list[str] = []
    expect_operand = True
    for token in tokens:
        if expect_operand:
            if not isinstance(token, str):
                instructions.append(token)
                expect_operand = False
            elif token in ("+", "-"):
                operators.append("u" + token)
            elif token == "(":
                operators.append(token)
            else:
                raise FormulaError("Неверная формула.")
        elif token == ")":
            while operators and operators[-1] != "(":
                instructions.append(operators.pop())
            if not operators:
                raise FormulaError("Лишняя закрывающая скобка.")
            operators.pop()
        elif isinstance(token, str) and token in PRECEDENCE:
            precedence = PRECEDENCE[token]
            while operators and operators[-1] != "(":
                previous = OPERATOR_PRECEDENCE[operators[-1]]
                if previous < precedence or (previous == precedence and token == "**"):
                    break
                instructions.append(operators.pop())
            operators.append(token)
            expect_operand = True
        else:
            raise FormulaError("Неверная формула.")

    if expect_operand:
        raise FormulaError("Неверная формула.")
    while operators:
        symbol = operators.pop()
        if symbol == "(":
            raise FormulaError("Не хватает закрывающей скобки.")
        instructions.append(symbol)
    return instructions


def _evaluate_count(tokens: Iterable[re.Match[str]]) -> int | float:
    values: list[int | float] = []
    for item in _compile(_plain_token(token) for token in tokens):
        if isinstance(item, Number):
            values.append(item.value)
        elif isinstance(item, str) and item in UNARY_OPERATORS:
            values.append(UNARY_OPERATORS[item](values.pop()))
        else:
            assert isinstance(item, str)
            right = values.pop()
            values.append(calculate(item, values.pop(), right))
    return values.pop()


class Parser:
    def __init__(self, text: str):
        self.tokens = list(TOKEN_RE.finditer(text))
        self.index = 0
        self.rolls = 0

    def peek(self) -> str:
        return self.tokens[self.index].group() if self.index < len(self.tokens) else ""

    def take(self) -> re.Match[str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def count_argument(self) -> list[re.Match[str]]:
        self.take()  # Opening parenthesis.
        start = self.index
        depth = 1
        while self.index < len(self.tokens):
            symbol = self.take().group()
            if symbol == "(":
                depth += 1
            elif symbol == ")":
                depth -= 1
                if depth == 0:
                    return self.tokens[start:self.index - 1]
        raise FormulaError("Не хватает закрывающей скобки.")

    def dice(self, token: re.Match[str]) -> Dice:
        notation = DICE_RE.fullmatch(token.group())
        if notation is None:
            raise FormulaError("Неверная запись кубика. Для преимущества — d20kh, для помехи — d20kl.")

        count_text, sides_text, keep, kept_text = notation.groups()
        sides_error = "Допустимые кубики — d4, d6, d8, d10, d12, d20 и d100."
        sides = _bounded_int(sides_text, max(DICE_SIDES), sides_error)
        if sides not in DICE_SIDES:
            raise FormulaError(sides_error)

        rolls_error = f"Максимум {MAX_DICE_PER_EXPRESSION} кубиков в формуле."
        count = _bounded_int(count_text, MAX_DICE_PER_EXPRESSION, rolls_error) if count_text else None
        if self.peek() == "(" and self.tokens[self.index].start() == token.end():
            argument = self.count_argument()
            if argument:
                if count is not None:
                    raise FormulaError("Укажи количество кубиков один раз.")
                count = _evaluate_count(argument)
            closing = self.tokens[self.index - 1]
            if keep is None and self.peek() and self.tokens[self.index].start() == closing.end():
                suffix = KEEP_RE.fullmatch(self.peek())
                if suffix is not None:
                    keep, kept_text = suffix.groups()
                    self.take()

        if count is None:
            count = 2 if keep and kept_text is None else 1
        if not isinstance(count, int) or count < 0:
            raise FormulaError("Количество кубиков должно быть целым числом от нуля.")
        self.rolls += count
        if self.rolls > MAX_DICE_PER_EXPRESSION:
            raise FormulaError(rolls_error)

        kept = count
        if keep:
            keep_error = "kh/kl должны оставлять от одного до числа брошенных кубиков."
            kept = _bounded_int(kept_text, count, keep_error) if kept_text is not None else 1
            if not 1 <= kept <= count:
                raise FormulaError(keep_error)
        return Dice(sides, count, keep.lower() if keep else None, kept)

    def atoms(self) -> list[Instruction]:
        atoms: list[Instruction] = []
        while self.index < len(self.tokens):
            token = self.take()
            atoms.append(self.dice(token) if token.lastgroup == "dice" else _plain_token(token))
        return atoms


def parse_formula(text: str) -> list[Instruction]:
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise FormulaError(f"Максимальная длина формулы — {MAX_EXPRESSION_LENGTH} символов.")
    instructions = _compile(Parser(text).atoms())
    if not any(isinstance(item, Dice) for item in instructions):
        raise FormulaError("В формуле нужен хотя бы один кубик.")
    return instructions
