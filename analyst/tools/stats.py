"""Statistics the analyst can run on a previous query result. Pure functions over DataFrames that return
plain markdown text (and, for forecasts, a Plotly figure). No model-written code is ever executed: the
agent picks a tool and column names, nothing else.

Every function reports problems as text so the model can correct itself, and states the sample size,
because a p-value without n is how analysts fool themselves.
"""

from itertools import combinations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

MAX_PAIRS = 12
MAX_OUTLIER_ROWS = 10


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series | str:
    if column not in frame.columns:
        return f"Column '{column}' not in {list(frame.columns)}."
    series = pd.to_numeric(frame[column], errors="coerce")
    if series.notna().sum() == 0:
        return f"Column '{column}' has no numeric values."
    return series


def _p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def _strength(r: float) -> str:
    a = abs(r)
    word = (
        "very weak"
        if a < 0.2
        else "weak"
        if a < 0.4
        else "moderate"
        if a < 0.6
        else "strong"
        if a < 0.8
        else "very strong"
    )
    return f"{word} {'positive' if r > 0 else 'negative'}"


# ------------------------------------------------------------------------------ correlation
def correlate(frame: pd.DataFrame, columns: list[str] | None = None, method: str = "pearson") -> str:
    if method not in ("pearson", "spearman"):
        return "method must be 'pearson' or 'spearman'."
    cols = columns or [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        return f"Unknown columns {missing}. Available: {list(frame.columns)}."
    if len(cols) < 2:
        return "Need at least two numeric columns to correlate."

    func = stats.pearsonr if method == "pearson" else stats.spearmanr
    rows = []
    for a, b in combinations(cols, 2):
        pair = pd.DataFrame(
            {a: pd.to_numeric(frame[a], errors="coerce"), b: pd.to_numeric(frame[b], errors="coerce")}
        ).dropna()
        if len(pair) < 3 or pair[a].nunique() < 2 or pair[b].nunique() < 2:
            continue
        r, p = func(pair[a], pair[b])
        rows.append(
            {
                "column_a": a,
                "column_b": b,
                "r": round(float(r), 3),
                "p_value": _p(p),
                "n": len(pair),
                "reading": _strength(r),
            }
        )
    if not rows:
        return "No column pair has at least 3 rows with variation."
    rows.sort(key=lambda row: -abs(row["r"]))
    table = pd.DataFrame(rows[:MAX_PAIRS]).to_markdown(index=False)
    return (
        f"{method.title()} correlation (strongest first):\n\n{table}\n\nCorrelation does not show causation."
    )


# --------------------------------------------------------------------------- group comparison
def compare_groups(frame: pd.DataFrame, value_column: str, group_column: str) -> str:
    values = _numeric(frame, value_column)
    if isinstance(values, str):
        return values
    if group_column not in frame.columns:
        return f"Column '{group_column}' not in {list(frame.columns)}."
    data = pd.DataFrame({"g": frame[group_column].astype(str), "v": values}).dropna()
    groups = {name: g["v"].to_numpy() for name, g in data.groupby("g") if len(g) >= 2}
    if len(groups) < 2:
        return "Need at least two groups with 2+ rows each."

    summary = (
        data[data["g"].isin(groups)]
        .groupby("g")["v"]
        .agg(n="count", mean="mean", median="median", std="std")
        .round(3)
        .reset_index()
    )
    parts = [f"Comparing {value_column} across {group_column}:\n\n{summary.to_markdown(index=False)}\n"]
    arrays = list(groups.values())
    if len(arrays) == 2:
        a, b = arrays
        t, p = stats.ttest_ind(a, b, equal_var=False)
        u_p = stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
        pooled = np.sqrt(
            ((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2)
        )
        d = (a.mean() - b.mean()) / pooled if pooled else 0.0
        parts.append(f"Welch t-test: t={t:.3f}, p={_p(p)}. Mann-Whitney U: p={_p(u_p)}. Cohen's d={d:.2f}.")
        significant = p < 0.05
    else:
        f, p = stats.f_oneway(*arrays)
        h_p = stats.kruskal(*arrays).pvalue
        grand = np.concatenate(arrays)
        ss_between = sum(len(x) * (x.mean() - grand.mean()) ** 2 for x in arrays)
        ss_total = ((grand - grand.mean()) ** 2).sum()
        eta = ss_between / ss_total if ss_total else 0.0
        parts.append(
            f"One-way ANOVA: F={f:.3f}, p={_p(p)}. Kruskal-Wallis: p={_p(h_p)}. eta squared={eta:.3f}."
        )
        significant = p < 0.05
    verdict = "differ significantly" if significant else "do not differ significantly"
    parts.append(
        f"At the 5% level the groups {verdict}. Small samples and many comparisons weaken this conclusion."
    )
    return "\n".join(parts)


# ------------------------------------------------------------------------------------ outliers
def find_outliers(
    frame: pd.DataFrame, column: str, method: str = "iqr", threshold: float | None = None
) -> str:
    values = _numeric(frame, column)
    if isinstance(values, str):
        return values
    clean = values.dropna()
    if len(clean) < 4:
        return "Need at least 4 numeric values."
    if method == "iqr":
        k = 1.5 if threshold is None else threshold
        q1, q3 = clean.quantile([0.25, 0.75])
        spread = q3 - q1
        low, high = q1 - k * spread, q3 + k * spread
        rule = f"IQR rule (k={k}): outside [{low:,.3f}, {high:,.3f}]"
    elif method == "zscore":
        k = 3.0 if threshold is None else threshold
        mean, std = clean.mean(), clean.std(ddof=1)
        if not std:
            return f"'{column}' is constant, so it has no outliers."
        low, high = mean - k * std, mean + k * std
        rule = f"z-score rule (|z|>{k}): outside [{low:,.3f}, {high:,.3f}]"
    else:
        return "method must be 'iqr' or 'zscore'."

    mask = (values < low) | (values > high)
    found = frame[mask.fillna(False)]
    head = f"{rule}. {len(found)} of {len(clean)} values are outliers."
    if found.empty:
        return head
    shown = found.assign(**{column: values[found.index]}).head(MAX_OUTLIER_ROWS)
    more = f"\n... {len(found) - len(shown)} more" if len(found) > len(shown) else ""
    return f"{head}\n\n{shown.to_markdown(index=False)}{more}"


# ----------------------------------------------------------------------------------- forecast
def forecast(
    frame: pd.DataFrame, time_column: str, value_column: str, periods: int = 3
) -> tuple[str, go.Figure | None]:
    """Linear-trend extrapolation with a 95% prediction interval. Deliberately simple and labelled as such."""
    if not 1 <= periods <= 24:
        return "periods must be between 1 and 24.", None
    values = _numeric(frame, value_column)
    if isinstance(values, str):
        return values, None
    if time_column not in frame.columns:
        return f"Column '{time_column}' not in {list(frame.columns)}.", None

    raw = frame[time_column]
    stamps = pd.to_datetime(raw, errors="coerce")
    is_date = stamps.notna().mean() > 0.9 and not pd.api.types.is_numeric_dtype(raw)
    x_raw = stamps if is_date else pd.to_numeric(raw, errors="coerce")
    data = pd.DataFrame({"x": x_raw, "y": values}).dropna().sort_values("x").reset_index(drop=True)
    if len(data) < 6:
        return f"Need at least 6 data points to forecast, got {len(data)}.", None

    t = np.arange(len(data), dtype=float)  # evenly spaced steps; the average spacing extends the axis
    y = data["y"].to_numpy(dtype=float)
    slope, intercept, r, _, _ = stats.linregress(t, y)
    fitted = intercept + slope * t
    dof = len(t) - 2
    resid_sd = np.sqrt(((y - fitted) ** 2).sum() / dof)
    t_future = np.arange(len(data), len(data) + periods, dtype=float)
    se = resid_sd * np.sqrt(1 + 1 / len(t) + (t_future - t.mean()) ** 2 / ((t - t.mean()) ** 2).sum())
    crit = stats.t.ppf(0.975, dof)
    pred = intercept + slope * t_future
    low, high = pred - crit * se, pred + crit * se

    if is_date:
        step = data["x"].diff().median()
        future_x = [data["x"].iloc[-1] + step * (i + 1) for i in range(periods)]
        labels = [pd.Timestamp(v).strftime("%Y-%m-%d") for v in future_x]
    else:
        step = data["x"].diff().median()
        future_x = [data["x"].iloc[-1] + step * (i + 1) for i in range(periods)]
        labels = [f"{v:g}" for v in future_x]

    table = pd.DataFrame(
        {time_column: labels, "forecast": pred.round(3), "lower_95": low.round(3), "upper_95": high.round(3)}
    )
    direction = "rising" if slope > 0 else "falling" if slope < 0 else "flat"
    text = (
        f"Linear trend on {len(data)} points: {direction} by {slope:,.3f} per step, R squared={r**2:.3f}.\n\n"
        f"{table.to_markdown(index=False)}\n\n"
        "This extrapolates a straight line. It ignores seasonality and one-off events, so treat it as a rough guide."
    )
    fig = go.Figure()
    fig.add_scatter(x=data["x"], y=y, mode="lines+markers", name="history")
    fig.add_scatter(x=future_x, y=pred, mode="lines+markers", name="forecast", line={"dash": "dash"})
    fig.add_scatter(
        x=future_x + future_x[::-1],
        y=list(high) + list(low[::-1]),
        fill="toself",
        line={"width": 0},
        name="95% interval",
        opacity=0.2,
    )
    fig.update_layout(
        title=f"{value_column}: trend forecast",
        template="plotly_white",
        margin={"t": 60, "l": 10, "r": 10, "b": 10},
    )
    return text, fig
