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


def _normal_ppf(p: float) -> float:
    """Inverse CDF (quantile function) of the standard normal distribution.
    Acklam's algorithm — accurate to ~1e-9, no scipy dependency.
    """
    if not 0 < p < 1:
        return float("nan")
    a = [-3.969683028665376e+01,  2.209460984245205e+02, -2.759285104469687e+02,
          1.383577518672690e+02, -3.066479806614716e+01,  2.506628277459239e+00]
    b = [-5.447609879822406e+01,  1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00,  4.374664141464968e+00,  2.938163982698783e+00]
    d = [ 7.784695709041462e-03,  3.224671290700398e-01,  2.445134137142996e+00,
          3.754408661907416e+00]
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= 1 - p_low:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1-p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def recover_se_from_p(effect: float | None, p_value: float | None, p_floor: float = 0.001) -> float | None:
    """Back out the standard error of an effect from a two-sided p-value using
    normal approximation: SE = |effect| / z(1 - p/2).

    Used as a fallback when the subagent didn't emit `se` or `t_stat` directly.
    Clamps p to [p_floor, 1 - p_floor] so an upstream-reported p=0 (below resolution)
    doesn't collapse the CI to a point estimate — instead we get a conservative SE
    that says "the test was at least this significant" without claiming more.

    Returns None for inputs we genuinely cannot recover from (missing values, zero
    effect — which is undefined for SE recovery).
    """
    if effect is None or p_value is None:
        return None
    try:
        eff = float(effect)
        p = float(p_value)
    except (TypeError, ValueError):
        return None
    if eff == 0:
        return None
    p_clamped = max(p_floor, min(1 - p_floor, p))
    z = _normal_ppf(1 - p_clamped / 2)
    if z == 0 or math.isnan(z):
        return None
    return abs(eff) / z


def compose_funnel_ci(m1uv_pct: float | None, m1uv_se_pct: float | None,
                      clicks_pct: float | None, clicks_se_pct: float | None,
                      alpha: float = 0.10) -> dict | None:
    """Compose AB margin-per-visitor %Δ with SEO clicks DiD %Δ into a joint
    Net Margin-per-Traffic %Δ, with a (1 - alpha) confidence interval via the
    delta method on the product (1 + m)(1 + c) - 1.

    Inputs are in PERCENT (e.g. 1.79 for +1.79%, not 0.0179). SEs are in PERCENT
    POINTS on those same percent quantities.

    Assumes independence between the two effects. This is an approximation —
    in reality the two are measured on overlapping populations and the same
    time window so some correlation exists. For typical experiments the
    independence-based CI is within a few percent of the true CI; flag if a
    use case ever needs joint covariance.

    Returns None when both effects are None (nothing to compose). When one
    effect is present and the other is None, treats the missing one as 0%
    effect with 0 SE (degrades to a single-axis CI). When effects are present
    but SEs are not, returns the point estimate with se=None and lower/upper=None
    so the caller can fall back to a label-based rule.
    """
    if m1uv_pct is None and clicks_pct is None:
        return None

    m = (m1uv_pct or 0.0) / 100.0
    c = (clicks_pct or 0.0) / 100.0
    point_pct = ((1 + m) * (1 + c) - 1) * 100.0

    have_se = (m1uv_se_pct is not None) and (clicks_se_pct is not None)
    # When EITHER component effect is genuinely missing (None), its SE
    # contribution is naturally zero, so a single-sided SE is meaningful.
    # Relax `have_se` accordingly so we don't drop into the label-matrix
    # fallback when one signal is just absent.
    if not have_se:
        if m1uv_pct is None and clicks_se_pct is not None:
            have_se = True
        if clicks_pct is None and m1uv_se_pct is not None:
            have_se = True

    if not have_se:
        return {
            "point": point_pct, "se": None, "lower": None, "upper": None,
            "z": None, "alpha": alpha,
        }

    sm = (m1uv_se_pct or 0.0) / 100.0
    sc = (clicks_se_pct or 0.0) / 100.0
    var = (1 + c) ** 2 * sm ** 2 + (1 + m) ** 2 * sc ** 2
    se_pct = math.sqrt(var) * 100.0
    z = _normal_ppf(1 - alpha / 2)
    return {
        "point": point_pct,
        "se": se_pct,
        "lower": point_pct - z * se_pct,
        "upper": point_pct + z * se_pct,
        "z": z,
        "alpha": alpha,
    }
