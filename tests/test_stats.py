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
