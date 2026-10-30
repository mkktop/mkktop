import importlib.util
from datetime import date, timedelta
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("profile", Path(__file__).resolve().parents[1] / "scripts/render_profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ActivityTests(unittest.TestCase):
    def test_current_streak_allows_an_unfinished_today(self):
        today = date(2026, 10, 30)
        days = {today - timedelta(days=i): 1 for i in [1, 2, 3, 5]}
        self.assertEqual(profile.streaks(days, today), (3, 3))
        days[today] = 2
        self.assertEqual(profile.streaks(days, today), (4, 4))

    def test_longest_streak_does_not_cross_a_missing_day(self):
        today = date(2026, 10, 30)
        days = {today - timedelta(days=i): 1 for i in [0, 2, 3, 4, 365, 366, 367, 368]}
        self.assertEqual(profile.streaks(days, today), (1, 3))

    def test_weekly_chart_uses_monday_boundaries(self):
        friday = date(2026, 10, 30)
        days = {date(2026, 10, 25): 5, date(2026, 10, 26): 2, friday: 7}
        self.assertEqual(profile.weekly_counts(days, friday, 2), [(date(2026, 10, 19), 5), (date(2026, 10, 26), 9)])

    def test_calendar_reads_zero_singular_and_comma_counts(self):
        first = date(2025, 11, 1)
        markup = ['<h2 id="js-contribution-activity-description">1,235 contributions in the last year</h2>']
        for i in range(365):
            label = "1,234 contributions" if i == 1 else "1 contribution" if i == 2 else "No contributions"
            markup.append(f'<td id="day-{i}" data-date="{first + timedelta(days=i)}"></td><tool-tip for="day-{i}">{label} on a date.</tool-tip>')
        parser = profile.Contributions()
        parser.feed("".join(markup))
        calendar = parser.calendar()
        self.assertEqual(parser.total, 1235)
        self.assertEqual(calendar[first], 0)
        self.assertEqual(calendar[first + timedelta(days=1)], 1234)
        self.assertEqual(calendar[first + timedelta(days=2)], 1)

    def test_incomplete_calendar_is_rejected_instead_of_becoming_zero(self):
        parser = profile.Contributions()
        parser.feed('<h2 id="js-contribution-activity-description">20 contributions</h2><td id="a" data-date="2026-10-30"></td>')
        with self.assertRaises(ValueError):
            parser.calendar()


if __name__ == "__main__":
    unittest.main()
