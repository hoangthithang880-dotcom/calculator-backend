"""安全数学表达式解析器：只识别数字与明确定义的数学语法。"""

import re
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext

MAX_LENGTH = 256
MAX_DEPTH = 40
NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
SYMBOLS = str.maketrans({"−": "-", "×": "*", "÷": "/"})


class ExpressionError(ValueError):
    """向前端提供稳定的错误代码与可读提示。"""

    def __init__(self, message, code="INVALID_EXPRESSION", position=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


def tokenize(expression):
    if not isinstance(expression, str):
        raise ExpressionError("表达式必须是文字", "INVALID_INPUT")
    if len(expression) > MAX_LENGTH:
        raise ExpressionError("表达式最多允许 256 个字符", "INPUT_TOO_LONG")
    text = expression.translate(SYMBOLS)
    if not text.strip():
        raise ExpressionError("请先输入表达式", "EMPTY_EXPRESSION")
    tokens = []
    position = 0
    while position < len(text):
        char = text[position]
        if char.isspace():
            position += 1
            continue
        match = NUMBER.match(text, position)
        if match:
            tokens.append(Token("NUMBER", match.group(), position))
            position = match.end()
        elif text.startswith("sqrt", position):
            tokens.append(Token("SQRT", "sqrt", position))
            position += 4
        elif char == "√":
            tokens.append(Token("SQRT", char, position))
            position += 1
        elif char in "+-*/()^%":
            tokens.append(Token(char, char, position))
            position += 1
        else:
            raise ExpressionError(
                f"第 {position + 1} 个字符「{char}」不受支持",
                "INVALID_CHARACTER",
                position,
            )
    tokens.append(Token("EOF", "", len(text)))
    return tokens


def check_range(value):
    """限制数值规模，避免极大指数或极小数消耗过多资源。"""
    if not value.is_finite() or (value and abs(value.adjusted()) > 100):
        raise ExpressionError("计算结果超出支持范围（指数绝对值不超过 100）", "OUT_OF_RANGE")
    return value


class Parser:
    """expression → term → unary → power → postfix → primary。"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    @property
    def current(self):
        return self.tokens[self.index]

    def accept(self, kind):
        if self.current.kind != kind:
            return False
        self.index += 1
        return True

    def parse(self):
        value = self.expression()
        if self.current.kind != "EOF":
            if self.current.kind == ")":
                raise ExpressionError(
                    "存在多余的右括号", "UNMATCHED_PARENTHESES", self.current.position
                )
            raise ExpressionError("数字、括号或函数之间需要运算符", position=self.current.position)
        return value

    def expression(self):
        value = self.term()
        while self.current.kind in ("+", "-"):
            operator = self.current.kind
            self.index += 1
            right = self.term()
            value = check_range(value + right if operator == "+" else value - right)
        return value

    def term(self):
        value = self.unary()
        while self.current.kind in ("*", "/"):
            operator = self.current.kind
            self.index += 1
            right = self.unary()
            if operator == "/" and right == 0:
                raise ExpressionError("不能除以零", "DIVISION_BY_ZERO")
            value = check_range(value * right if operator == "*" else value / right)
        return value

    def unary(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExpressionError("括号、正负号或幂的嵌套过深", "TOO_DEEP")
        try:
            if self.accept("+"):
                return self.unary()
            if self.accept("-"):
                return -self.unary()
            return self.power()
        finally:
            self.depth -= 1

    def power(self):
        value = self.postfix()
        if self.accept("^"):
            # 右结合：2^3^2 = 2^(3^2)。一元负号优先级低于幂。
            exponent = self.unary()
            if exponent != exponent.to_integral_value() or abs(exponent) > 100:
                raise ExpressionError("幂运算的指数必须是 -100 到 100 的整数", "INVALID_EXPONENT")
            if value == 0 and exponent <= 0:
                raise ExpressionError("零的非正整数次幂未定义", "DOMAIN_ERROR")
            value = check_range(value ** int(exponent))
        return value

    def postfix(self):
        value = self.primary()
        while self.accept("%"):
            value = check_range(value / Decimal(100))
        return value

    def primary(self):
        token = self.current
        if self.accept("NUMBER"):
            return check_range(Decimal(token.value))
        if self.accept("("):
            value = self.expression()
            if not self.accept(")"):
                raise ExpressionError(
                    "缺少右括号 )", "UNMATCHED_PARENTHESES", self.current.position
                )
            return value
        if self.accept("SQRT"):
            if not self.accept("("):
                raise ExpressionError(
                    "平方根需要写成 sqrt(9) 或 √(9)", position=self.current.position
                )
            value = self.expression()
            if not self.accept(")"):
                raise ExpressionError("平方根缺少右括号 )", "UNMATCHED_PARENTHESES")
            if value < 0:
                raise ExpressionError("平方根的数字不能为负数", "DOMAIN_ERROR")
            return check_range(value.sqrt())
        message = "表达式尚未完成，请补充数字" if token.kind == "EOF" else "这里需要数字或左括号"
        raise ExpressionError(
            message,
            "INCOMPLETE_EXPRESSION" if token.kind == "EOF" else "INVALID_EXPRESSION",
            token.position,
        )


def evaluate_expression(expression):
    """40 位十进制精度；拒绝任意代码、未知函数与不完整输入。"""
    tokens = tokenize(expression)
    try:
        with localcontext() as context:
            context.prec = 40
            return check_range(Parser(tokens).parse())
    except DecimalException as error:
        raise ExpressionError("数字格式或计算范围不受支持", "NUMERIC_ERROR") from error


def format_number(value):
    """最多 24 位有效数字；过大过小的数使用科学计数法。"""
    if value == 0:
        return "0"
    text = format(value, ".24g")
    mantissa, separator, exponent = text.partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    return mantissa + (separator + exponent if separator else "")
