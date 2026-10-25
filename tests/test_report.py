"""Independent correctness checks for report formatting."""

import unittest

from src.report import format_report


class ReportTests(unittest.TestCase):
    def test_formats_counts_deterministically(self):
        self.assertEqual(format_report("Unit tests", 4, 4), "Unit tests: 4/4 checks passed")

    def test_rejects_empty_title(self):
        with self.assertRaises(ValueError):
            format_report("  ", 0, 0)

    def test_rejects_inconsistent_counts(self):
        with self.assertRaises(ValueError):
            format_report("Unit tests", 3, 2)


if __name__ == "__main__":
    unittest.main()
