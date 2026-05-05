"""Statistical helpers for AB/SEO evaluation."""
from __future__ import annotations
import math
from statistics import mean, stdev
from typing import Sequence


def paired_ttest(control: Sequence[float], treatment: Sequence[float]) -> dict:
    if len(control) != len(treatment):
        raise ValueError(f"length mismatch: {len(control)} vs {len(treatment)}")
    n = len(control)
    diffs = [t - c for c, t in zip(control, treatment)]
    mean_delta = sum(diffs) / n
    if all(d == diffs[0] for d in diffs):
        # constant diff -> std=0 -> handle via t=inf if delta!=0 else 0
        if mean_delta == 0:
            return {"n": n, "mean_delta": 0.0, "t_stat": 0.0, "p_value": 1.0, "se": 0.0}
        return {"n": n, "mean_delta": mean_delta, "t_stat": float("inf"), "p_value": 0.0, "se": 0.0}
    sd = stdev(diffs)
    se = sd / math.sqrt(n)
    t = mean_delta / se if se else 0.0
    # Two-sided p-value via Student's t survival; use math.erf-based approx for normal
    # since scipy may not be available in plugin sandbox. Sufficient for n>=30.
    p = 2 * (1 - _normal_cdf(abs(t)))
    return {"n": n, "mean_delta": mean_delta, "t_stat": t, "p_value": max(0.0, min(1.0, p)), "se": se}


def cohens_d(control: Sequence[float], treatment: Sequence[float]) -> float:
    nc, nt = len(control), len(treatment)
    if nc < 2 or nt < 2:
        return 0.0
    mc, mt = mean(control), mean(treatment)
    sc, st = stdev(control), stdev(treatment)
    pooled = math.sqrt(((nc - 1) * sc**2 + (nt - 1) * st**2) / (nc + nt - 2))
    if pooled == 0:
        return 0.0
    return (mt - mc) / pooled


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def srm_chi_square(observed: dict, expected_share: dict, alpha: float = 0.001) -> dict:
    """Chi-square SRM check. SRM uses tight α=0.001 (industry standard)."""
    if set(observed) != set(expected_share):
        raise ValueError(f"keys mismatch: {set(observed)} vs {set(expected_share)}")
    n = sum(observed.values())
    chi = 0.0
    for k in observed:
        exp_n = n * expected_share[k]
        if exp_n <= 0:
            raise ValueError(f"expected count <=0 for {k}")
        chi += (observed[k] - exp_n) ** 2 / exp_n
    df = len(observed) - 1
    p = _chi_square_sf(chi, df)
    return {
        "chi_sq": chi,
        "df": df,
        "p_value": p,
        "alpha": alpha,
        "verdict": "fail" if p < alpha else "pass",
        "observed": dict(observed),
        "expected_n": {k: n * v for k, v in expected_share.items()},
    }


def did(pre_treat: Sequence[float], post_treat: Sequence[float],
        pre_ctrl: Sequence[float], post_ctrl: Sequence[float]) -> float:
    """DiD = (post_treat_avg - pre_treat_avg) - (post_ctrl_avg - pre_ctrl_avg).
    Returned in same units as input (typically percent points after pre-indexing to 100)."""
    return (mean(post_treat) - mean(pre_treat)) - (mean(post_ctrl) - mean(pre_ctrl))


def _chi_square_sf(x: float, df: int) -> float:
    """Survival function (1 - CDF) for chi-square. Uses regularized upper incomplete gamma."""
    if x <= 0:
        return 1.0
    # Wilson-Hilferty cube-root approximation — good enough for SRM (df typically 1-3, x large when fail)
    h = 2 / (9 * df)
    z = ((x / df) ** (1/3) - (1 - h)) / math.sqrt(h)
    return 1 - _normal_cdf(z)
