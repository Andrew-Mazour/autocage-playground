"""Independent correctness checks for the calculator task."""

import unittest

from src.calculator import add, multiply, subtract


class CalculatorTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_multiply(self):
        self.assertEqual(multiply(6, 7), 42)

    def test_subtract(self):
        self.assertEqual(subtract(9, 4), 5)


if __name__ == "__main__":
    unittest.main()
