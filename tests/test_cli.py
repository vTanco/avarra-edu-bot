from datetime import datetime

from navarra_edu_bot.cli import compute_next_target


def test_compute_next_target_same_day_before_target():
    now = datetime(2026, 4, 27, 13, 45)

    target = compute_next_target(now, 14, 0)

    assert target == datetime(2026, 4, 27, 14, 0)


def test_compute_next_target_rolls_to_next_day_after_target():
    now = datetime(2026, 4, 24, 14, 28)

    target = compute_next_target(now, 14, 0)

    assert target == datetime(2026, 4, 25, 14, 0)
