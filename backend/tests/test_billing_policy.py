from datetime import datetime, timezone

import pytest

from app.core.errors import PermissionDenied, QuotaExceeded, ValidationFailed
from app.services.billing.plans import PLANS
from app.services.billing.policy import UsageSnapshot, check_quota, estimate_tokens, month_start, pick_provider

FREE, PRO, TEAM = PLANS["free"], PLANS["pro"], PLANS["team"]
NOON = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def test_free_plan_gets_ollama_even_if_the_global_default_is_paid():
    assert pick_provider(FREE, None, default="anthropic", fallback="ollama") == "ollama"


def test_free_plan_cannot_ask_for_a_paid_provider():
    with pytest.raises(PermissionDenied) as err:
        pick_provider(FREE, "anthropic", default="ollama", fallback="ollama")
    assert err.value.code == "provider_not_in_plan"


def test_pro_plan_can_pick_any_provider():
    assert pick_provider(PRO, "deepseek", default="ollama", fallback="ollama") == "deepseek"
    assert pick_provider(PRO, None, default="anthropic", fallback="ollama") == "anthropic"


def test_under_the_daily_cap_is_fine():
    check_quota(FREE, UsageSnapshot(FREE.daily_request_limit - 1, 0), input_chars=100, now=NOON)


def test_daily_cap_blocks_with_retry_after_until_midnight_utc():
    with pytest.raises(QuotaExceeded) as err:
        check_quota(FREE, UsageSnapshot(FREE.daily_request_limit, 0), input_chars=100, now=NOON)
    assert err.value.code == "daily_limit_reached"
    assert err.value.headers["Retry-After"] == str(12 * 3600)


def test_monthly_tokens_block():
    with pytest.raises(QuotaExceeded) as err:
        check_quota(PRO, UsageSnapshot(0, PRO.monthly_token_limit), input_chars=100, now=NOON)
    assert err.value.code == "monthly_tokens_reached"


def test_team_is_unlimited():
    check_quota(TEAM, UsageSnapshot(10_000, 10**9), input_chars=100, now=NOON)


def test_input_size_is_checked_per_plan():
    with pytest.raises(ValidationFailed):
        check_quota(FREE, UsageSnapshot(0, 0), input_chars=FREE.max_input_chars + 1, now=NOON)
    check_quota(PRO, UsageSnapshot(0, 0), input_chars=FREE.max_input_chars + 1, now=NOON)


def test_helpers():
    assert month_start(NOON) == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100
