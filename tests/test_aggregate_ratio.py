"""Tests for the aggregate-ratio enforcement in render.stats_for_daily and
render._recompute_view_metrics.

Canonical contract: %Δ = SUM(num)/SUM(den) (ab-experiments plugin canon). Daily-mean
percentages are not produced under any circumstance — neither as the primary value nor
as a fallback. A subagent that emits a daily-mean pct gets it overridden by the renderer.
"""
from scripts.lib.render import stats_for_daily, _recompute_view_metrics, build_payload


def _two_day_daily_with_skew():
    """Daily rows where the aggregate ratio diverges visibly from a daily-mean ratio.
    Day 1: ctrl 100 / 1000 = 0.10, treat 110 / 1000 = 0.11      (10% lift)
    Day 2: ctrl  10 /  100 = 0.10, treat  12 /  100 = 0.12      (20% lift)
    Daily-mean of ratios:    ctrl 0.10, treat 0.115 → +15.0%
    Aggregate (SUM/SUM):     ctrl 110/1100=0.10, treat 122/1100≈0.1109 → +10.91%
    """
    return [
        {"d": "2026-01-01", "m1uv_ctrl": 0.10, "m1uv_treat": 0.11,
         "m1_ctrl": 100, "m1_treat": 110, "uv_ctrl": 1000, "uv_treat": 1000,
         "cvr_ctrl": 0.05, "cvr_treat": 0.06,
         "orders_ctrl": 50, "orders_treat": 60, "udv_ctrl": 1000, "udv_treat": 1000},
        {"d": "2026-01-02", "m1uv_ctrl": 0.10, "m1uv_treat": 0.12,
         "m1_ctrl": 10, "m1_treat": 12, "uv_ctrl": 100, "uv_treat": 100,
         "cvr_ctrl": 0.05, "cvr_treat": 0.07,
         "orders_ctrl": 5, "orders_treat": 7, "udv_ctrl": 100, "udv_treat": 100},
    ]


def test_stats_for_daily_returns_aggregate_ratio_not_daily_mean():
    out = stats_for_daily(_two_day_daily_with_skew(), "m1uv")
    assert out is not None
    # Aggregate: 122/1100 / (110/1100) - 1 = 12/11 * 1 ≈ 0.0909 → +9.09%
    # (Not 0.0915 = daily mean of (1.10x, 1.20x) - 1.)
    assert abs(out["mean_delta_pct"] - 10.909) < 0.05, out["mean_delta_pct"]
    # Aggregate cleanup: no daily_mean_pct field leaks through.
    assert "daily_mean_pct" not in out


def test_stats_for_daily_no_totals_returns_none():
    """Subagent emits ratios only — function refuses the daily-mean fallback."""
    daily = [{"d": "2026-01-01", "m1uv_ctrl": 0.10, "m1uv_treat": 0.11},
             {"d": "2026-01-02", "m1uv_ctrl": 0.10, "m1uv_treat": 0.12}]
    assert stats_for_daily(daily, "m1uv") is None


def test_stats_for_daily_empty_returns_none():
    assert stats_for_daily([], "m1uv") is None
    assert stats_for_daily(None, "m1uv") is None


def test_stats_for_daily_cvr_uses_orders_over_udv():
    out = stats_for_daily(_two_day_daily_with_skew(), "cvr")
    assert out is not None
    # SUM(orders)=55c / 67t, SUM(udv)=1100/1100. Aggregate ctrl=0.0500, treat=0.0609 → +21.8%
    # (Daily mean of ratios would be (20% + 40%)/2 = +30%; verifies aggregate path.)
    assert 21 < out["mean_delta_pct"] < 23, out["mean_delta_pct"]


def test_recompute_overrides_subagent_daily_mean_pct():
    """Subagent stamped a daily-mean pct on the m1uv block; the renderer must overwrite
    it with the aggregate-ratio pct."""
    view = {
        "daily": _two_day_daily_with_skew(),
        # Subagent's incorrect (daily-mean) pct.
        "m1uv": {"mean_delta_pct": 15.0, "p_value": 0.42, "subagent_marker": "kept"},
        "cvr": {"mean_delta_pct": 25.0, "p_value": 0.30},
    }
    _recompute_view_metrics(view)
    # m1uv overwritten with aggregate ratio.
    assert abs(view["m1uv"]["mean_delta_pct"] - 10.909) < 0.05
    # Subagent extras are preserved.
    assert view["m1uv"]["subagent_marker"] == "kept"
    # cvr also recomputed (aggregate: 67/55 - 1 = +21.8%, not the 25% subagent stamp).
    assert 21 < view["cvr"]["mean_delta_pct"] < 23


def test_recompute_handles_nested_stats_block():
    """raw.filtered shape: m1uv lives under view.stats.m1uv, not view.m1uv."""
    view = {
        "daily": _two_day_daily_with_skew(),
        "stats": {"m1uv": {"mean_delta_pct": 99.0, "p_value": 0.5}},
    }
    _recompute_view_metrics(view)
    assert abs(view["stats"]["m1uv"]["mean_delta_pct"] - 10.909) < 0.05


def test_recompute_skips_when_totals_missing():
    """Daily rows have ratios but no underlying totals — original block is left alone
    (the renderer treats it as missing rather than fall back to daily mean)."""
    view = {
        "daily": [{"d": "2026-01-01", "m1uv_ctrl": 0.10, "m1uv_treat": 0.11}],
        "m1uv": {"mean_delta_pct": "untouched", "p_value": 0.5},
    }
    _recompute_view_metrics(view)
    assert view["m1uv"]["mean_delta_pct"] == "untouched"


def test_build_payload_recomputes_per_category():
    """End-to-end: a subagent emits a per_category cat with daily-mean pct; build_payload
    must replace it with aggregate ratio."""
    exp = {
        "ab": {
            "raw": {"filtered": {"daily": [], "stats": {}, "verdict": "?"}, "overall": {}},
            "per_category": {
                "Food & Drink": {
                    "daily": _two_day_daily_with_skew(),
                    "m1uv": {"mean_delta_pct": 15.0, "p_value": 0.42},
                    "cvr": {"mean_delta_pct": 25.0, "p_value": 0.30},
                    "denominator": "uv",
                }
            },
        }
    }
    payload = build_payload("xp-test", exp, "run", "2026-01-02")
    pc = payload["per_category"]["Food & Drink"]
    assert abs(pc["m1uv"]["mean_delta_pct"] - 10.909) < 0.05
    assert 21 < pc["cvr"]["mean_delta_pct"] < 23
