"""必做数学规则、扩展功能、错误输入和资源限制。"""

import unittest
from decimal import Decimal

from src.calculator import ExpressionError, evaluate_expression, format_number


class CalculatorTests(unittest.TestCase):
    def test_assignment_examples(self):
        cases = {
            "12+8": "20",
            "8-3": "5",
            "7*8": "56",
            "7/2": "3.5",
            "1+2*3": "7",
            "(1+2)*3": "9",
            "10/2+7": "12",
            "8-3*2": "2",
            "-5+8": "3",
            "3*-2": "-6",
            "+5 + +2": "7",
            "0.1+0.2": "0.3",
            ".5+1.": "1.5",
            "((2+3)*(4-1))/5": "3",
            "1-(2-(3-4))": "-2",
            "8/2/2": "2",
            "8-3-2": "3",
            "3 × −2": "-6",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(format_number(evaluate_expression(expression)), expected)

    def test_extensions(self):
        cases = {
            "2^3^2": "512",
            "-2^2": "-4",
            "(-2)^2": "4",
            "2^-3": "0.125",
            "sqrt(9)": "3",
            "√(9)+2^3": "11",
            "50%": "0.5",
            "100+10%": "100.1",
            "(20+30)%": "0.5",
            "1e-3+1": "1.001",
            "sqrt(sqrt(16))": "2",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(format_number(evaluate_expression(expression)), expected)

    def test_invalid_expressions(self):
        cases = [
            "",
            " ",
            "1+",
            "()",
            "1..2",
            "2(3+4)",
            "(1+2",
            "1+2)",
            "3*/2",
            "1 2",
            "1e",
            "sqrt9",
            "sqrt()",
            "3//2",
            "2**3",
        ]
        for expression in cases:
            with self.subTest(expression=expression):
                with self.assertRaises(ExpressionError):
                    evaluate_expression(expression)

    def test_rejects_arbitrary_code(self):
        cases = [
            "__import__('os')",
            "open('file')",
            "[1,2]",
            "1;2",
            "lambda:1",
            "sin(0)",
            "<script>",
        ]
        for expression in cases:
            with self.subTest(expression=expression):
                with self.assertRaises(ExpressionError):
                    evaluate_expression(expression)

    def test_division_by_zero(self):
        with self.assertRaises(ExpressionError) as raised:
            evaluate_expression("1/(2-2)")
        self.assertEqual(raised.exception.code, "DIVISION_BY_ZERO")

    def test_domain_and_resource_limits(self):
        for expression in [
            "sqrt(-1)",
            "0^0",
            "0^-1",
            "2^0.5",
            "2^101",
            "1e101",
            "1e-101",
            "9" * 257,
            "(" * 45 + "1" + ")" * 45,
        ]:
            with self.subTest(expression=expression):
                with self.assertRaises(ExpressionError):
                    evaluate_expression(expression)

    def test_format_and_reuse(self):
        self.assertEqual(format_number(Decimal("100.000")), "100")
        self.assertEqual(format_number(Decimal("-0")), "0")
        text = format_number(evaluate_expression("1/3"))
        self.assertTrue(text.startswith("0.333333333"))
        self.assertEqual(evaluate_expression(text), Decimal(text))


if __name__ == "__main__":
    unittest.main()
