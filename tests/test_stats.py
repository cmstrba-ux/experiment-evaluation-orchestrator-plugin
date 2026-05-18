import pytest
from scripts.lib.stats import paired_ttest, cohens_d

def test_paired_ttest_identical_arrays():
    r = paired_ttest([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert r["p_value"] == 1.0
    assert r["t_stat"] == 0.0
    assert r["mean_delta"] == 0.0

def test_paired_ttest_clear_lift():
    control = [1.0, 1.0, 1.0, 1.0, 1.0]
    treatment = [2.0, 2.0, 2.0, 2.0, 2.0]
    r = paired_ttest(control, treatment)
    assert r["mean_delta"] == 1.0
    assert r["p_value"] < 0.001  # large clear effect

def test_paired_ttest_length_mismatch_raises():
    with pytest.raises(ValueError, match="length"):
        paired_ttest([1, 2], [1, 2, 3])

def test_cohens_d_no_effect():
    assert abs(cohens_d([1, 2, 3], [1, 2, 3])) < 1e-9

def test_cohens_d_known_value():
    # Two groups: control mean=10, treatment mean=12, pooled sd≈1 → d≈2
    d = cohens_d([9, 10, 11], [11, 12, 13])
    assert 1.5 < d < 2.5


from scripts.lib.stats import srm_chi_square, did

def test_srm_passes_clean_split():
    # 50/50 expected, observed 5000/5050 → not significant
    r = srm_chi_square({"control": 5000, "treatment": 5050}, {"control": 0.5, "treatment": 0.5})
    assert r["verdict"] == "pass"

def test_srm_fails_skewed_split():
    # 50/50 expected, observed 5000/3000 → significant SRM
    r = srm_chi_square({"control": 5000, "treatment": 3000}, {"control": 0.5, "treatment": 0.5})
    assert r["verdict"] == "fail"

def test_srm_three_arm():
    r = srm_chi_square(
        {"control": 3300, "v1": 3400, "v2": 3300},
        {"control": 1/3, "v1": 1/3, "v2": 1/3},
    )
    assert r["verdict"] == "pass"

def test_did_zero_effect():
    pre_treat = [100, 100, 100]
    post_treat = [100, 100, 100]
    pre_ctrl = [200, 200, 200]
    post_ctrl = [200, 200, 200]
    assert abs(did(pre_treat, post_treat, pre_ctrl, post_ctrl)) < 1e-9

def test_did_treatment_lift():
    # Treatment +20%, Control flat → DiD ≈ +20pp
    pre_treat = [100]
    post_treat = [120]
    pre_ctrl = [100]
    post_ctrl = [100]
    d = did(pre_treat, post_treat, pre_ctrl, post_ctrl)
    assert abs(d - 20.0) < 0.01


# ---- compose_funnel_ci ------------------------------------------------------
from scripts.lib.stats import compose_funnel_ci, recover_se_from_p, _normal_ppf

def test_normal_ppf_known_quantiles():
    # 95% one-sided → z = 1.6449
    assert abs(_normal_ppf(0.95) - 1.6449) < 1e-3
    # 97.5% → z = 1.9600
    assert abs(_normal_ppf(0.975) - 1.9600) < 1e-3
    # Median → z = 0
    assert abs(_normal_ppf(0.5)) < 1e-6

def test_recover_se_simple():
    # Effect=2.0, p≈0.0455 → z≈2 → SE≈1.0
    se = recover_se_from_p(effect=2.0, p_value=0.0455)
    assert 0.95 < se < 1.05

def test_recover_se_clamps_p_zero():
    # p=0 should clamp to p_floor=0.001 → z≈3.29 → SE≈|effect|/3.29
    se = recover_se_from_p(effect=-4.0, p_value=0.0)
    assert se is not None and 1.15 < se < 1.30

def test_recover_se_missing_returns_none():
    assert recover_se_from_p(None, 0.05) is None
    assert recover_se_from_p(1.0, None) is None
    assert recover_se_from_p(0.0, 0.05) is None  # zero effect → undefined

def test_compose_funnel_ci_returns_none_when_both_missing():
    assert compose_funnel_ci(None, None, None, None) is None

def test_compose_funnel_ci_point_estimate_no_se():
    # Effects provided, SEs missing → point but no CI bounds
    r = compose_funnel_ci(m1uv_pct=1.79, m1uv_se_pct=None,
                          clicks_pct=-4.0, clicks_se_pct=None)
    assert r["point"] is not None
    assert abs(r["point"] - ((1.0179 * 0.96 - 1) * 100)) < 1e-6
    assert r["lower"] is None and r["upper"] is None

def test_compose_funnel_ci_faq_reviews_worked_example():
    # FAQ reviews actual values: m1uv +1.79% SE 1.72, clicks DiD -4.03% SE 1.22
    # Expected: point ≈ -2.28%, 90% CI ≈ [-5.6%, +1.1%] (HOLD under MWSE=0.5%)
    r = compose_funnel_ci(m1uv_pct=1.79, m1uv_se_pct=1.72,
                          clicks_pct=-4.03, clicks_se_pct=1.22,
                          alpha=0.10)
    assert -2.5 < r["point"] < -2.0
    # CI should straddle zero (this is the test case that should NOT trip the CI rule)
    assert r["lower"] < 0 < r["upper"]
    # SE should be ~2pp
    assert 1.8 < r["se"] < 2.3

def test_compose_funnel_ci_clear_deploy():
    # Both axes positive and significant → CI entirely above 0
    r = compose_funnel_ci(m1uv_pct=5.0, m1uv_se_pct=0.5,
                          clicks_pct=3.0, clicks_se_pct=0.4,
                          alpha=0.10)
    assert r["lower"] > 0  # significantly positive
    assert r["point"] > 7.5

def test_compose_funnel_ci_clear_kill():
    # Both axes negative and significant → CI entirely below 0
    r = compose_funnel_ci(m1uv_pct=-3.0, m1uv_se_pct=0.4,
                          clicks_pct=-5.0, clicks_se_pct=0.5,
                          alpha=0.10)
    assert r["upper"] < 0  # significantly negative
    assert r["point"] < -7.5


# ---- _compose_final_verdict (decision hierarchy) ----------------------------
from scripts.lib.render import _compose_final_verdict

def _base_signals(**over):
    s = {
        "ab_verdict": "HOLD",
        "m1uv_pct": 0.0, "m1uv_p": 0.5, "m1uv_t": 0.5, "m1uv_n": 20,
        "cvr_pct": 0.0,  "cvr_p": 0.5,
        "seo_status": "ok", "seo_verdict": "INCONCLUSIVE",
        "seo_signal_strength": "full",
        "did_imp_pct": 0.0, "did_clicks_pct": 0.0, "did_clicks_p": 0.5,
        "srm_verdict": "pass",
    }
    s.update(over)
    return s

def test_verdict_guardrail_seo_impressions_full_signal_kills():
    # AB SHIP but SEO impressions at full signal < -10% → KILL guardrail
    r = _compose_final_verdict(_base_signals(
        ab_verdict="SHIP", m1uv_pct=5.0, m1uv_t=4.0,
        did_imp_pct=-15.0, did_clicks_pct=-3.0, did_clicks_p=0.001,
    ))
    assert r["verdict"] == "KILL"
    assert r["basis"] == "guardrail"
    assert "ranking-risk" in r["rationale"] or "impressions" in r["rationale"].lower()

def test_verdict_guardrail_cvr_significantly_negative_kills():
    # AB CVR significantly negative → KILL guardrail
    r = _compose_final_verdict(_base_signals(
        ab_verdict="SHIP", m1uv_pct=5.0, m1uv_t=4.0,
        cvr_pct=-2.0, cvr_p=0.01,
    ))
    assert r["verdict"] == "KILL"
    assert r["basis"] == "guardrail"

def test_verdict_ci_deploy_when_lower_above_mwse():
    # Composed lower > +0.5% → DEPLOY via CI rule
    r = _compose_final_verdict(_base_signals(
        ab_verdict="SHIP", m1uv_pct=5.0, m1uv_t=10.0,  # SE ≈ 0.5pp
        seo_verdict="POSITIVE",
        did_imp_pct=3.0, did_clicks_pct=3.0, did_clicks_p=0.001,  # SE ≈ ~0.9pp
    ))
    assert r["verdict"] == "DEPLOY"
    assert r["basis"] == "ci"

def test_verdict_ci_kill_when_upper_below_neg_mwse():
    # Composed upper < -0.5% → KILL via CI rule (no guardrail trip)
    r = _compose_final_verdict(_base_signals(
        ab_verdict="KILL", m1uv_pct=-5.0, m1uv_t=-10.0,
        seo_verdict="INCONCLUSIVE",
        did_imp_pct=-3.0, did_clicks_pct=-3.0, did_clicks_p=0.001,
    ))
    assert r["verdict"] == "KILL"
    assert r["basis"] == "ci"

def test_verdict_ci_hold_when_ci_straddles():
    # FAQ reviews shape — point near zero, CI straddles → HOLD
    # BUT this case also trips the SEO impressions guardrail in real life;
    # use a smaller impressions DiD so we isolate the CI rule.
    r = _compose_final_verdict(_base_signals(
        ab_verdict="HOLD", m1uv_pct=1.0, m1uv_t=1.0,  # SE ≈ 1pp
        seo_verdict="INCONCLUSIVE",
        did_imp_pct=-5.0,  # within guardrail threshold
        did_clicks_pct=-2.0, did_clicks_p=0.20,
    ))
    assert r["verdict"] == "HOLD"
    assert r["basis"] == "ci"

def test_verdict_falls_back_to_matrix_when_no_se():
    # No t_stat AND no p → no SE recovery → matrix fallback
    r = _compose_final_verdict(_base_signals(
        ab_verdict="SHIP", m1uv_pct=2.0, m1uv_p=None, m1uv_t=None,
        seo_status="no_urls", seo_verdict=None, did_clicks_pct=None,
    ))
    # SHIP × MISSING SEO → DEPLOY per matrix
    assert r["verdict"] == "DEPLOY"
    assert r["basis"] == "matrix"

def test_verdict_faq_reviews_real_data_kills_via_guardrail():
    # Reproduce the worked example from the user-facing methodology answer:
    # AB m1uv +1.79% (p=0.311, t=1.04), CVR +5.5% (p=0.26, not negative),
    # SEO PAUSE with impressions DiD -16% at full signal.
    # Expected verdict: KILL via SEO impressions guardrail.
    r = _compose_final_verdict(_base_signals(
        ab_verdict="KILL",
        m1uv_pct=1.79, m1uv_p=0.311, m1uv_t=1.04, m1uv_n=20,
        cvr_pct=5.52, cvr_p=0.257,
        seo_verdict="PAUSE", seo_signal_strength="full",
        did_imp_pct=-16.05, did_clicks_pct=-4.03, did_clicks_p=0.0,
    ))
    assert r["verdict"] == "KILL"
    assert r["basis"] == "guardrail"
    # Composed CI should still be computed and surfaced even though guardrail decided.
    assert r["composed_point"] is not None
    assert -3.0 < r["composed_point"] < -1.5  # ~-2.3% per the worked example
