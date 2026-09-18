"""Covariance estimation and constrained minimum-variance optimisation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def ledoit_wolf(returns: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Ledoit-Wolf (2004) shrinkage towards a constant-correlation target.

    Returns the shrunk covariance (same units as the input, i.e. per period)
    and the shrinkage intensity delta in [0, 1].
    """
    X = returns.dropna().to_numpy(dtype=float)
    t, n = X.shape
    X = X - X.mean(axis=0)
    S = X.T @ X / t
    var = np.diag(S)
    std = np.sqrt(var)
    corr = S / np.outer(std, std)
    rbar = (corr.sum() - n) / (n * (n - 1))
    F = rbar * np.outer(std, std)
    np.fill_diagonal(F, var)

    # pi-hat: sum of asymptotic variances of the sample covariance entries
    Y = X ** 2
    pi_mat = Y.T @ Y / t - S ** 2
    pi_hat = pi_mat.sum()
    # rho-hat
    term1 = (X ** 3).T @ X / t
    term2 = np.outer(var, np.ones(n)) * S
    theta_ii = term1 - term2            # theta_{ii,ij}
    theta_jj = theta_ii.T               # theta_{jj,ij}
    rho_off = (rbar / 2) * (
        np.outer(1 / std, std) * theta_ii + np.outer(std, 1 / std) * theta_jj
    )
    np.fill_diagonal(rho_off, 0.0)
    rho_hat = np.diag(pi_mat).sum() + rho_off.sum()
    gamma_hat = np.linalg.norm(F - S, "fro") ** 2
    kappa = (pi_hat - rho_hat) / gamma_hat if gamma_hat > 0 else 0.0
    delta = float(np.clip(kappa / t, 0.0, 1.0))
    sigma = delta * F + (1 - delta) * S
    cols = returns.columns
    return pd.DataFrame(sigma, index=cols, columns=cols), delta


def min_variance(
    cov: pd.DataFrame,
    max_weight: float = 0.25,
    group_min: dict[str, tuple[list[str], float]] | None = None,
    x0: np.ndarray | None = None,
) -> pd.Series:
    """Long-only, fully invested minimum-variance weights.

    group_min maps a label to (tickers, minimum total weight), e.g.
    {"equity": (["IVV", "IEFA"], 0.20)}.
    """
    names = list(cov.index)
    n = len(names)
    C = cov.to_numpy(dtype=float) * 1e4  # scale for numerical stability
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones_like(w)}]
    for _, (tickers, floor) in (group_min or {}).items():
        mask = np.array([1.0 if t in tickers else 0.0 for t in names])
        if mask.sum() == 0:
            continue
        cons.append({"type": "ineq", "fun": lambda w, m=mask, f=floor: m @ w - f, "jac": lambda w, m=mask: m})
    ub = max(max_weight, 1.0 / n + 1e-9)
    bounds = [(0.0, ub)] * n
    if x0 is None:
        x0 = np.full(n, 1.0 / n)
    res = minimize(
        lambda w: w @ C @ w,
        x0,
        jac=lambda w: 2 * C @ w,
        bounds=bounds,
        constraints=cons,
        method="SLSQP",
        options={"maxiter": 500, "ftol": 1e-12},
    )
    w = np.clip(res.x, 0.0, None)
    w = w / w.sum()
    return pd.Series(w, index=names)


def risk_contributions(weights: pd.Series, cov: pd.DataFrame) -> pd.DataFrame:
    """Euler decomposition of portfolio volatility.

    Returns marginal contribution, contribution to vol (sums to portfolio vol)
    and percentage contribution (sums to 1).
    """
    w = weights.reindex(cov.index).fillna(0.0).to_numpy()
    C = cov.to_numpy()
    port_var = w @ C @ w
    vol = np.sqrt(port_var)
    mcr = C @ w / vol
    ctr = w * mcr
    return pd.DataFrame(
        {"weight": w, "mcr": mcr, "ctr": ctr, "pct": ctr / vol}, index=cov.index
    )
