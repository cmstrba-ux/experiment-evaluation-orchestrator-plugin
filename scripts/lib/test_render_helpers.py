"""Unit tests for new render.py helpers introduced for upstream-SEO migration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render import (
    _seo_overall_ctr_did_pp,
    _seo_l2_row_lookup,
    _seo_l2_ctr_did_pp,
    _seo_days_since_release,
)


def test_seo_days_anchored_on_run_date_not_data_through():
    """Regression: the countdown must advance with the run date, not freeze at
    (end_date - release). The 1/14-forever bug passed data_through = end_date =
    release+1 while the run happened 10 days later — must read 10, not 1."""
    # run_id = 2026-05-22-09-23, release 2026-05-12, data_through (AB end) 2026-05-13
    assert _seo_days_since_release("2026-05-22-09-23", "2026-05-12", "2026-05-13") == 10
    # Same release/window, later run date → strictly larger (not frozen).
    assert _seo_days_since_release("2026-05-30-00-00", "2026-05-12", "2026-05-13") == 18


def test_seo_days_falls_back_to_through_without_run_date():
    """Idempotency fixture passes run_id='run' (no date prefix) → fall back to
    data_through so behavior stays deterministic and non-crashing."""
    assert _seo_days_since_release("run", "2026-05-12", "2026-05-19") == 7
    assert _seo_days_since_release("run", "2026-05-12", "(unknown)") is None


def test_seo_days_clamps_negative_and_handles_missing():
    # Release after the run date → clamped to 0, never negative.
    assert _seo_days_since_release("2026-05-12-00-00", "2026-05-20", "2026-05-20") == 0
    assert _seo_days_since_release("2026-05-22-09-23", None, "2026-05-13") is None
    assert _seo_days_since_release("2026-05-22-09-23", "not-a-date", "2026-05-13") is None


def test_overall_ctr_did_pp_basic():
    """CTR DiD pp = (variant_post_ctr - variant_pre_ctr) - (whole_post_ctr - whole_pre_ctr), in pp."""
    summary_tables = {
        "overall": [
            {"label": "Variant",
             "pre_impressions": 1000, "post_impressions": 1200,
             "pre_clicks": 100, "post_clicks": 150},
            {"label": "Whole Groupon (groupon.com / core)",
             "pre_impressions": 100000, "post_impressions": 110000,
             "pre_clicks": 5000, "post_clicks": 5400},
        ]
    }
    # Variant: pre_ctr=0.10, post_ctr=0.125 → +0.025
    # Whole:   pre_ctr=0.05, post_ctr=0.0491 → −0.0009
    # DiD pp = (0.025 − (−0.0009)) × 100 ≈ 2.59pp
    result = _seo_overall_ctr_did_pp(summary_tables)
    assert result is not None
    assert abs(result - 2.59) < 0.05, result


def test_overall_ctr_did_pp_missing_whole_returns_none():
    summary_tables = {"overall": [{"label": "Variant",
        "pre_impressions": 1000, "post_impressions": 1200,
        "pre_clicks": 100, "post_clicks": 150}]}
    assert _seo_overall_ctr_did_pp(summary_tables) is None


def test_overall_ctr_did_pp_zero_denominator_returns_none():
    summary_tables = {"overall": [
        {"label": "Variant", "pre_impressions": 0, "post_impressions": 1200, "pre_clicks": 0, "post_clicks": 150},
        {"label": "Whole Groupon", "pre_impressions": 100000, "post_impressions": 110000, "pre_clicks": 5000, "post_clicks": 5400},
    ]}
    assert _seo_overall_ctr_did_pp(summary_tables) is None


def test_overall_ctr_did_pp_empty_input():
    assert _seo_overall_ctr_did_pp({}) is None
    assert _seo_overall_ctr_did_pp({"overall": []}) is None
    assert _seo_overall_ctr_did_pp(None) is None


def test_l2_row_lookup_finds_variant_row_by_l2_name():
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Beauty & Spas / Massages",
                     "did_impr_pp": 3.1, "did_clicks_pp": 1.9,
                     "pre_impressions": 100, "post_impressions": 120,
                     "pre_clicks": 10, "post_clicks": 13},
                    {"label": "All Groupon — L2: Beauty & Spas / Massages",
                     "pre_impressions": 9000, "post_impressions": 9100,
                     "pre_clicks": 500, "post_clicks": 510},
                ],
            }
        }
    }
    row = _seo_l2_row_lookup(summary_tables, "Massages")
    assert row is not None
    assert row["did_impr_pp"] == 3.1
    assert row["did_clicks_pp"] == 1.9


def test_l2_row_lookup_missing_returns_none():
    summary_tables = {"by_category": {"L2": {"available": True, "rows": []}}}
    assert _seo_l2_row_lookup(summary_tables, "Massages") is None
    assert _seo_l2_row_lookup({}, "Massages") is None


def test_l2_row_lookup_handles_no_slash_label():
    """Single-component L2 labels (no '/' separator) should still match by suffix."""
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Food",
                     "did_impr_pp": 4.2, "did_clicks_pp": 2.1,
                     "pre_impressions": 100, "post_impressions": 130,
                     "pre_clicks": 10, "post_clicks": 14},
                ],
            }
        }
    }
    row = _seo_l2_row_lookup(summary_tables, "Food")
    assert row is not None
    assert row["did_impr_pp"] == 4.2


def test_l2_ctr_did_pp_uses_paired_all_groupon_row():
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Beauty / Massages",
                     "pre_impressions": 1000, "post_impressions": 1200,
                     "pre_clicks": 100, "post_clicks": 150},
                    {"label": "All Groupon — L2: Beauty / Massages",
                     "pre_impressions": 100000, "post_impressions": 110000,
                     "pre_clicks": 5000, "post_clicks": 5400},
                ],
            }
        }
    }
    result = _seo_l2_ctr_did_pp(summary_tables, "Massages")
    assert result is not None
    assert abs(result - 2.59) < 0.05, result


def test_l2_row_lookup_resolves_ttd_alias():
    """AB-side abbreviation 'TTD' should match upstream label 'Things to Do'."""
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Local / Things to Do",
                     "did_impr_pp": 7.7, "did_clicks_pp": 4.4,
                     "pre_impressions": 200, "post_impressions": 230,
                     "pre_clicks": 20, "post_clicks": 25},
                ],
            }
        }
    }
    row = _seo_l2_row_lookup(summary_tables, "TTD")
    assert row is not None
    assert row["did_impr_pp"] == 7.7


def test_l2_row_lookup_resolves_hbw_alias():
    """AB-side abbreviation 'HBW' should match upstream label 'Beauty & Spas'."""
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Local / Beauty & Spas",
                     "did_impr_pp": 2.2, "did_clicks_pp": 1.1,
                     "pre_impressions": 100, "post_impressions": 110,
                     "pre_clicks": 10, "post_clicks": 12},
                ],
            }
        }
    }
    row = _seo_l2_row_lookup(summary_tables, "HBW")
    assert row is not None
    assert row["did_clicks_pp"] == 1.1


def test_l2_ctr_did_pp_no_pair_returns_none():
    summary_tables = {
        "by_category": {
            "L2": {
                "available": True,
                "rows": [
                    {"label": "Variant — L2: Beauty / Massages",
                     "pre_impressions": 1000, "post_impressions": 1200,
                     "pre_clicks": 100, "post_clicks": 150},
                ],
            }
        }
    }
    assert _seo_l2_ctr_did_pp(summary_tables, "Massages") is None


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            fails += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    raise SystemExit(fails)
