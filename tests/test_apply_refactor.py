import inspect

import pytest

from navarra_edu_bot.scraper import apply as apply_mod


def test_prewarm_and_fire_are_exported():
    assert hasattr(apply_mod, "prewarm_application_context")
    assert hasattr(apply_mod, "fire_submission")
    assert inspect.iscoroutinefunction(apply_mod.prewarm_application_context)
    assert inspect.iscoroutinefunction(apply_mod.fire_submission)


def test_apply_to_offers_still_exported_for_backcompat():
    assert hasattr(apply_mod, "apply_to_offers")
    assert inspect.iscoroutinefunction(apply_mod.apply_to_offers)
