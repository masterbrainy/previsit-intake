"""Eval runner settings (PROGRESS 1.10): the app's models can be overridden per run, and the simulated patient and
judges stay fixed so comparisons between model settings are fair."""
from __future__ import annotations

import pytest

from evals.run import JUDGE_MODEL, SIM_MODEL, apply_overrides, eval_model_for


def test_overrides_change_only_the_named_settings(settings):
    updated = apply_overrides(settings, ["interview_model=gpt-fast", "safety_model=gpt-faster"])

    assert updated.interview_model == "gpt-fast" and updated.safety_model == "gpt-faster"
    assert updated.extraction_model == settings.extraction_model


@pytest.mark.parametrize("bad", ["interview_model", "no_such_setting=x", "=x"])
def test_bad_overrides_are_rejected(settings, bad):
    with pytest.raises(ValueError):
        apply_overrides(settings, [bad])


def test_simulator_and_judges_do_not_follow_the_app_model_settings():
    assert eval_model_for("sim_patient") == SIM_MODEL
    assert eval_model_for("judge_sheet") == JUDGE_MODEL
    assert eval_model_for("judge_support") == JUDGE_MODEL
