"""
spc_laney_engine.py  (v2)
=========================
SPC engine for the anonymized plant inspection data set.

What changed vs v1
------------------
* Every number shown on a chart or written to JSON/markdown is COMPUTED here.
  No hard-coded labels such as "~7.6%" or "n=916".
* Laney-adjusted significance (z, p, CI) and batch-level robust tests
  (Mann-Whitney, Welch, cluster bootstrap) are computed for the overall
  result and for the two SKUs that exist in both phases.
* Rolling trend is volume-weighted and never crosses the phase boundary.
* Run rule (8 consecutive batches above the center line) added.
* Charts: readable (capped) UCL, standard-vs-Laney breaches marked,
  SKU-stratified p-charts, monthly view with overdispersion-adjusted CIs,
  capability histogram with truncation diagnostics, aligned Pareto.

Outputs
-------
dashboard/pipe_cover_laney_spc_chart.png      overview p'-chart
dashboard/pipe_cover_laney_by_sku.png         SKU-stratified p'-charts
dashboard/pipe_cover_monthly_trend.png        monthly reject rate with CI
dashboard/pipe_cover_density_capability.png   density histogram + Cp/Cpk
dashboard/pipe_cover_pareto_anonymized.png    aligned Pareto, pre vs post
data/processed/statistical_evaluation_summary.json
data/processed/results_table.md               table to paste into README
"""
import json
import os
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from scipy import stats

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
LSL, USL = 220.0, 270.0            # density spec limits, kg/m3
UNIT_COST_IDR = 45_000             # ASSUMPTION: flat scrap cost per piece
PRE, POST = "Pre-Intervention", "Post-Intervention"
D2 = 1.128                         # moving-range constant for n = 2
Y_CAP = 40.0                       # display cap (%) for the overview chart
RUN_LEN = 8                        # run rule length
ROLL_N = 5                         # rolling window (batches)
N_BOOT = 5000
SEED = 42
COL = {PRE: "#C53030", POST: "#2B6CB0"}
SKU_FOCUS = ('6" 90', '8" 90')

plt.rcParams.update({"font.size": 10, "axes.titleweight": "bold"})


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------
def load(base):
    proc = os.path.join(base, "data", "processed")
    b = pd.read_csv(os.path.join(proc, "plant_insulation_batches_anonymized.csv"),
                    parse_dates=["date"])
    s = pd.read_csv(os.path.join(proc, "plant_density_samples_anonymized.csv"))
    # Stable sort: keeps the source row order inside a day (52 batches share a date),
    # so results are reproducible. sigma_z depends on this order -> see sigma_z_sensitivity().
    b = b.sort_values("date", kind="stable").reset_index(drop=True)
    b["p"] = b.reject_pcs / b.total_pcs
    return b, s, proc


# ----------------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------------
def two_prop(x1, n1, x2, n2):
    """Naive two-proportion z-test (assumes pieces are independent)."""
    p1, p2 = x1 / n1, x2 / n2
    pp = (x1 + x2) / (n1 + n2)
    se = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    return dict(p1=p1, p2=p2, diff=p1 - p2, se=se, z=z,
                p=2 * (1 - stats.norm.cdf(abs(z))))


def laney_limits(sub):
    """Laney p' limits for one phase / series (rows must be in time order)."""
    pbar = sub.reject_pcs.sum() / sub.total_pcs.sum()
    sig_i = np.sqrt(pbar * (1 - pbar) / sub.total_pcs)
    z = (sub.p - pbar) / sig_i
    sigma_z = float(np.mean(np.abs(np.diff(z.values))) / D2)
    out = pd.DataFrame(index=sub.index)
    out["p_bar"] = pbar
    out["ucl_std"] = pbar + 3 * sig_i
    out["lcl_std"] = np.maximum(0, pbar - 3 * sig_i)
    out["ucl_laney"] = pbar + 3 * sig_i * sigma_z
    out["lcl_laney"] = np.maximum(0, pbar - 3 * sig_i * sigma_z)
    return out, sigma_z


def sigma_z_sensitivity(df, n_perm=300, seed=SEED):
    """sigma_z uses moving ranges, so it depends on the order of batches that share a date.
    Re-compute it under random within-day orderings: returns [2.5%, 50%, 97.5%] per phase."""
    rng = np.random.default_rng(seed)
    out = {PRE: [], POST: []}
    for _ in range(n_perm):
        t = df.assign(_r=rng.random(len(df))).sort_values(["date", "_r"])
        for ph in (PRE, POST):
            out[ph].append(laney_limits(t[t.phase == ph])[1])
    return {ph: [float(np.percentile(v, q)) for q in (2.5, 50, 97.5)] for ph, v in out.items()}


def run_flags(p, center, k=RUN_LEN):
    flag = np.zeros(len(p), dtype=bool)
    run = 0
    for i, above in enumerate(p.values > center):
        run = run + 1 if above else 0
        if run >= k:
            flag[i] = True
    return flag


def cluster_bootstrap(pre, post, n_boot=N_BOOT, seed=SEED):
    """Resample BATCHES (not pieces) -> CI that respects overdispersion."""
    rng = np.random.default_rng(seed)
    a = pre[["reject_pcs", "total_pcs"]].to_numpy(float)
    c = post[["reject_pcs", "total_pcs"]].to_numpy(float)
    ia = rng.integers(0, len(a), (n_boot, len(a)))
    ic = rng.integers(0, len(c), (n_boot, len(c)))
    ra = a[ia, 0].sum(1) / a[ia, 1].sum(1)
    rc = c[ic, 0].sum(1) / c[ic, 1].sum(1)
    d = (ra - rc) * 100
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))], float((d <= 0).mean())


def batch_level(pre, post):
    ci, share = cluster_bootstrap(pre, post)
    return {
        "n_batches_pre": int(len(pre)), "n_batches_post": int(len(post)),
        "mannwhitney_p": float(stats.mannwhitneyu(pre.p, post.p).pvalue),
        "welch_p": float(stats.ttest_ind(pre.p, post.p, equal_var=False).pvalue),
        "boot_ci_diff_pp": ci,                      # pre - post, percentage points
        "boot_share_diff_le_0": share,
        "ci_excludes_zero": bool(ci[0] > 0 or ci[1] < 0),
    }


def sku_test(df, sku):
    d = df[df["size"] == sku]
    a, c = d[d.phase == PRE], d[d.phase == POST]
    t = two_prop(a.reject_pcs.sum(), a.total_pcs.sum(), c.reject_pcs.sum(), c.total_pcs.sum())
    bl = batch_level(a, c)
    return {
        "pre_reject_rate": t["p1"], "post_reject_rate": t["p2"],
        "pre_avg_batch_rate": float(a.p.mean()), "post_avg_batch_rate": float(c.p.mean()),
        "delta_pct": float((t["p2"] - t["p1"]) / t["p1"] * 100),
        "z_score_naive": float(t["z"]), "p_value_naive": float(t["p"]),
        "batch_level": bl,
        "robust_significant": bool(bl["ci_excludes_zero"] and bl["mannwhitney_p"] < 0.05),
        "pre_pcs": int(a.total_pcs.sum()), "post_pcs": int(c.total_pcs.sum()),
    }


def capability(d):
    d = d.dropna()
    mu, sd = float(d.mean()), float(d.std(ddof=1))
    cpu, cpl = (USL - mu) / (3 * sd), (mu - LSL) / (3 * sd)
    return {
        "sample_size": int(len(d)), "mean": mu, "std": sd,
        "cp": (USL - LSL) / (6 * sd), "cpu": cpu, "cpl": cpl, "cpk": min(cpu, cpl),
        "pct_below_lsl": float((d < LSL).mean() * 100),
        "pct_above_usl": float((d > USL).mean() * 100),
        "normal_pred_pct_below_lsl": float(stats.norm.cdf(LSL, mu, sd) * 100),
        "normal_pred_pct_above_usl": float(stats.norm.sf(USL, mu, sd) * 100),
        "min": float(d.min()), "max": float(d.max()),
        "n_at_min": int((d == d.min()).sum()), "n_at_max": int((d == d.max()).sum()),
        "skew": float(stats.skew(d)), "normaltest_p": float(stats.normaltest(d).pvalue),
    }


def wilson(x, n, z=1.96):
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return centre - half, centre + half


def monthly_table(df, sigma_z):
    rows = []
    months = pd.period_range(df.date.min(), df.date.max(), freq="M")
    for m in months:
        sub = df[df.date.dt.to_period("M") == m]
        if sub.empty:
            rows.append({"month": str(m), "batches": 0, "pcs": 0, "rejects": 0,
                         "rate": None, "ci_lo": None, "ci_hi": None, "phase": None})
            continue
        x, n = int(sub.reject_pcs.sum()), int(sub.total_pcs.sum())
        lo, hi = wilson(x, n)
        r = x / n
        # inflate the binomial half-widths by sigma_z (overdispersion)
        lo_a, hi_a = max(0.0, r - sigma_z * (r - lo)), min(1.0, r + sigma_z * (hi - r))
        rows.append({"month": str(m), "batches": int(len(sub)), "pcs": n, "rejects": x,
                     "rate": r, "ci_lo": lo_a, "ci_hi": hi_a,
                     "phase": sub.phase.mode().iloc[0]})
    return rows


# ----------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------
def _date_ticks(ax, dates, step):
    idx = np.arange(0, len(dates), step)
    ax.set_xticks(idx)
    ax.set_xticklabels([f"B#{i + 1}\n{dates.iloc[i]:%d-%b}" for i in idx], fontsize=8)


def chart_overview(df, sig, path):
    x = np.arange(len(df))
    pre_len = int((df.phase == PRE).sum())
    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(14, 8.6), sharex=True,
        gridspec_kw={"height_ratios": [3.4, 1], "hspace": 0.08})
    for a in (ax, axv):
        a.axvline(pre_len - 0.5, color="#2D3748", ls="--", lw=1.4)
    ax.axvspan(-0.5, pre_len - 0.5, color="#FFF5F5")
    ax.axvspan(pre_len - 0.5, len(df) - 0.5, color="#F0FFF4")

    for ph in (PRE, POST):
        m = (df.phase == ph).values
        ax.scatter(x[m], df.p[m] * 100, s=22, color=COL[ph], alpha=.6, zorder=3)
        ax.hlines(df.p_bar[m].iloc[0] * 100, x[m][0] - .5, x[m][-1] + .5,
                  color=COL[ph], lw=2, zorder=4)
        ax.plot(x[m], df.rolling_p5[m] * 100, color=COL[ph], lw=2.2, alpha=.85, zorder=4)
        ax.step(x[m], np.minimum(df.ucl_laney[m] * 100, Y_CAP), where="mid",
                color="#DD6B20", lw=1.6, zorder=2)
        ax.step(x[m], np.minimum(df.ucl_std[m] * 100, Y_CAP), where="mid",
                color="#4A5568", lw=1.2, ls=":", zorder=2)
        axv.bar(x[m], df.total_pcs[m], color=COL[ph], alpha=.55, width=.8)

    std_only = (df.ooc_std & ~df.ooc_laney).values
    ax.scatter(x[std_only], df.p[std_only] * 100, marker="x", s=48, color="#2D3748", zorder=6)
    run = df.run_rule.values
    ax.scatter(x[run], df.p[run] * 100, marker="D", s=70, facecolors="none",
               edgecolors="#D69E2E", linewidths=1.8, zorder=6)
    for i in np.where(df.ooc_laney.values)[0]:
        r = df.iloc[i]
        ax.scatter([i], [r.p * 100], s=190, facecolors="none", edgecolors="#9B2C2C",
                   linewidths=2.4, zorder=7)
        ax.annotate(f'{r["size"]}: {r.p:.1%} (n={int(r.total_pcs)})',
                    xy=(i, r.p * 100), xytext=(i - 12, min(r.p * 100 + 5, Y_CAP - 2)),
                    fontsize=8.5, fontweight="bold", color="#742A2A",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#9B2C2C"),
                    arrowprops=dict(arrowstyle="->", color="black", lw=1.4), zorder=8)

    ax.set_ylim(-1, Y_CAP)
    ax.set_xlim(-0.5, len(df) - 0.5)
    ax.set_ylabel("Batch reject rate (%)", fontweight="bold")
    ax.grid(True, ls="--", alpha=.35)
    ax.text(0.995, 0.015, f"UCL values above {Y_CAP:.0f}% are drawn at the frame edge (small batches)",
            transform=ax.transAxes, ha="right", fontsize=7.5, color="#4A5568")
    axv.set_ylabel("Pcs / batch", fontsize=9)
    axv.grid(True, ls=":", alpha=.4)
    _date_ticks(axv, df.date, 10)
    axv.set_xlabel("Batch sequence (chronological) - note uneven spacing in calendar time, see monthly chart",
                   fontweight="bold")

    handles = [
        Line2D([], [], marker="o", ls="", color=COL[PRE], alpha=.7, label="Batch - baseline"),
        Line2D([], [], marker="o", ls="", color=COL[POST], alpha=.7, label="Batch - post"),
        Line2D([], [], color="#2D3748", lw=2, label="Center line (pooled, per phase)"),
        Line2D([], [], color="#2D3748", lw=2.2, alpha=.6,
               label=f"Rolling {ROLL_N}-batch (volume-weighted)"),
        Line2D([], [], color="#DD6B20", lw=1.6, label="Laney UCL (p')"),
        Line2D([], [], color="#4A5568", lw=1.2, ls=":", label="Standard binomial UCL"),
        Line2D([], [], marker="o", ls="", mfc="none", mec="#9B2C2C", mew=2.2, ms=11,
               label=f"Laney breach (n={int(df.ooc_laney.sum())})"),
        Line2D([], [], marker="x", ls="", color="#2D3748", mew=1.8,
               label=f"Standard-only breach (n={int(std_only.sum())})"),
        Line2D([], [], marker="D", ls="", mfc="none", mec="#D69E2E", mew=1.8,
               label=f"Run rule: {RUN_LEN} above center (n={int(run.sum())})"),
    ]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=3,
              fontsize=8, frameon=False)
    fig.suptitle("LANEY p'-CHART - PIPE COVER REJECT RATE\n"
                 f"{len(df)} batches | sigma_z baseline {sig[PRE]:.2f}, post {sig[POST]:.2f} "
                 "(1.0 would mean no overdispersion)",
                 fontsize=12.5, fontweight="bold", y=0.995)
    fig.subplots_adjust(top=0.82, left=0.07, right=0.99, bottom=0.09)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def chart_by_sku(df, path):
    fig, axes = plt.subplots(len(SKU_FOCUS), 1, figsize=(14, 4.7 * len(SKU_FOCUS)))
    for ax, sku in zip(np.atleast_1d(axes), SKU_FOCUS):
        sub = df[df["size"] == sku].sort_values(["date", "batch_id"]).reset_index(drop=True)
        lim, sz = laney_limits(sub)
        x = np.arange(len(sub))
        ymax = float(min(max(sub.p.max() * 100 * 1.25, 12), 45))
        first_post = int((sub.phase == PRE).sum())
        ax.axvline(first_post - 0.5, color="#2D3748", ls="--", lw=1.4)
        ax.step(x, np.minimum(lim.ucl_laney * 100, ymax), where="mid", color="#DD6B20", lw=1.6)
        ax.step(x, np.minimum(lim.ucl_std * 100, ymax), where="mid", color="#4A5568", lw=1.1, ls=":")
        ax.axhline(lim.p_bar.iloc[0] * 100, color="#718096", lw=1, ls="-.")
        for ph in (PRE, POST):
            m = (sub.phase == ph).values
            ax.scatter(x[m], sub.p[m] * 100, s=34, color=COL[ph], alpha=.8, zorder=3,
                       label=f"{ph.split('-')[0]}: {sub.reject_pcs[m].sum() / sub.total_pcs[m].sum():.2%} "
                             f"({int(m.sum())} batches, {int(sub.total_pcs[m].sum()):,} pcs)")
            ax.hlines(sub.reject_pcs[m].sum() / sub.total_pcs[m].sum() * 100,
                      x[m][0] - .5, x[m][-1] + .5, color=COL[ph], lw=2.2, ls="--")
        br = (sub.p > lim.ucl_laney).values
        ax.scatter(x[br], sub.p[br] * 100, s=170, facecolors="none", edgecolors="#9B2C2C",
                   linewidths=2.2, zorder=5)
        ax.set_ylim(-0.5, ymax)
        ax.set_xlim(-0.5, len(sub) - 0.5)
        ax.set_ylabel("Batch reject rate (%)", fontweight="bold")
        ax.set_title(f'{sku} - p\'-chart, limits from all {len(sub)} batches of this SKU '
                     f'(sigma_z = {sz:.2f}); dashed = phase pooled rate', fontsize=11)
        ax.grid(True, ls="--", alpha=.35)
        ax.legend(loc="upper right", fontsize=8.5, frameon=True)
        _date_ticks(ax, sub.date, max(1, len(sub) // 8))
    fig.suptitle("SKU-STRATIFIED CONTROL CHARTS (the two SKUs present in both phases)",
                 fontsize=13, fontweight="bold", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def chart_monthly(rows, sigma_z, pooled, path):
    fig, ax = plt.subplots(figsize=(12, 5.6))
    for i, r in enumerate(rows):
        if r["batches"] == 0:
            ax.text(i, 0.4, "no batches\nin data", ha="center", va="bottom",
                    fontsize=8.5, color="#718096", style="italic")
            continue
        ax.bar(i, r["rate"] * 100, color=COL[r["phase"]], alpha=.8, width=.6)
        ax.errorbar(i, r["rate"] * 100,
                    yerr=[[r["rate"] * 100 - r["ci_lo"] * 100], [r["ci_hi"] * 100 - r["rate"] * 100]],
                    color="#1A202C", capsize=5, lw=1.3)
        ax.text(i, r["ci_hi"] * 100 + 0.5, f'{r["rate"]:.1%}\n{r["batches"]} batch{"es" if r["batches"] != 1 else ""}\n{r["pcs"]:,} pcs',
                ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    for ph in (PRE, POST):
        ax.axhline(pooled[ph] * 100, color=COL[ph], ls="--", lw=1.3, alpha=.8,
                   label=f'{ph.split("-")[0]} pooled rate: {pooled[ph]:.2%}')
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r["month"] for r in rows])
    ax.set_ylabel("Reject rate (%)", fontweight="bold")
    ax.set_ylim(0, max([r["ci_hi"] for r in rows if r["rate"] is not None]) * 100 * 1.35)
    ax.grid(axis="y", ls="--", alpha=.35)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("MONTHLY REJECT RATE - 95% CI widened by sigma_z for overdispersion\n"
                 "Shows how unevenly the data is spread over calendar time", fontsize=11.5)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def chart_density(df, s, caps, path):
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 6), sharey=True)
    bins = np.arange(200, 270.1, 5)
    xs = np.linspace(195, 280, 400)
    ymax = 0.0
    for ax, ph in zip(axes, (PRE, POST)):
        ids = set(df[df.phase == ph].batch_id)
        d = s[s.batch_id.isin(ids)].density_kgm3
        c = caps[ph]
        ax.axvspan(195, LSL, color="#FED7D7", alpha=.35)
        ax.axvspan(USL, 280, color="#FEEBC8", alpha=.45)
        ax.hist(d, bins=bins, density=True, color=COL[ph], alpha=.55, edgecolor="white")
        ax.plot(xs, stats.norm.pdf(xs, c["mean"], c["std"]), color=COL[ph], lw=2.2,
                label="Fitted normal (for reference)")
        ax.axvline(LSL, color="#C53030", ls="--", lw=1.8, label=f"LSL {LSL:.0f}")
        ax.axvline(USL, color="#C05621", ls="--", lw=1.8, label=f"USL {USL:.0f}")
        ymax = max(ymax, np.histogram(d, bins=bins, density=True)[0].max(),
                   stats.norm.pdf(c["mean"], c["mean"], c["std"]))
        ax.set_xlim(195, 280)
        ax.set_xlabel("Box bulk density (kg/m3)", fontweight="bold")
        ax.set_title(f'{ph.split("-")[0]} period - n = {c["sample_size"]:,} box measurements')
        txt = (f'Mean {c["mean"]:.1f} | Std {c["std"]:.2f}\n'
               f'Cp {c["cp"]:.2f} | Cpk {c["cpk"]:.2f}\n'
               f'Below LSL: observed {c["pct_below_lsl"]:.2f}% vs normal model {c["normal_pred_pct_below_lsl"]:.2f}%\n'
               f'Above USL: observed {c["pct_above_usl"]:.2f}% vs normal model {c["normal_pred_pct_above_usl"]:.2f}%\n'
               f'Range {c["min"]:.0f}-{c["max"]:.0f}; {c["n_at_max"]} readings exactly at {c["max"]:.0f}')
        ax.text(0.02, 0.97, txt, transform=ax.transAxes, va="top", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#A0AEC0"))
        ax.grid(True, ls=":", alpha=.4)
        ax.legend(loc="upper right", fontsize=8)
    axes[0].set_ylim(0, ymax * 1.62)             # headroom for the info boxes
    axes[0].set_ylabel("Probability density", fontweight="bold")
    allc = list(caps.values())
    note = ""
    if all(c["pct_above_usl"] == 0 for c in allc) and any(c["normal_pred_pct_above_usl"] > 0.5 for c in allc):
        note = ("Caution: no reading exceeds the USL although the normal model predicts "
                f'{max(c["normal_pred_pct_above_usl"] for c in allc):.1f}% - and values stop exactly at the spec '
                "edges. The data look capped/filtered; verify the extraction before trusting Cp/Cpk.")
    fig.suptitle("PROCESS CAPABILITY - BOX DENSITY (pooled over all SKUs; one spec for all)",
                 fontsize=13, fontweight="bold", y=0.99)
    if note:
        fig.text(0.5, 0.01, note, ha="center", fontsize=9, color="#742A2A", style="italic", wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def chart_pareto(df, dens_max, path):
    cats = list(df.defect_category.dropna().unique())
    palette = {c: plt.cm.tab10(i) for i, c in enumerate(cats)}
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 6))
    for ax, ph in zip(axes, (PRE, POST)):
        sub = df[df.phase == ph]
        cnt = sub.groupby("defect_category").reject_pcs.sum()
        cnt = cnt[cnt > 0].sort_values(ascending=False)
        total = float(cnt.sum())
        xs = np.arange(len(cnt))
        ax.bar(xs, cnt.values, color=[palette[c] for c in cnt.index], width=.6)
        ax.set_ylim(0, total)                      # left axis = total  -> aligned with right axis 0-100
        ax2 = ax.twinx()
        ax2.set_ylim(0, 100)
        ax2.plot(xs, cnt.cumsum().values / total * 100, color="#DD6B20", marker="o", lw=2.2)
        ax2.axhline(80, color="#E53E3E", ls="--", lw=1)
        ax2.set_ylabel("Cumulative %", color="#DD6B20", fontweight="bold")
        for xi, v in zip(xs, cnt.values):
            ax.text(xi, v + total * 0.012, f"{int(v)} pcs\n{v / total:.1%}", ha="center",
                    va="bottom", fontsize=8.5, fontweight="bold")
        ax.set_xticks(xs)
        ax.set_xticklabels(["\n".join(textwrap.fill(l, 16) for l in c.replace(" (", "\n(").split("\n")) for c in cnt.index], fontsize=8)
        ax.set_ylabel("Rejected pieces", fontweight="bold")
        ax.set_title(f'{ph.split("-")[0]}: {int(total):,} rejected pcs in {len(sub)} batches')
    note = ("Left axis spans 0 to the total, so the cumulative line starts at the top of the first bar. "
            "Each batch's rejects are attributed to ONE category taken from free-text inspector notes.")
    if dens_max <= USL:
        note += (f' "Excess density" is not corroborated by the density samples (max reading '
                 f'{dens_max:.0f} kg/m3, none above the USL).')
    fig.suptitle("PARETO OF REJECTS BY DEFECT CATEGORY - BASELINE vs POST", fontsize=13,
                 fontweight="bold", y=0.99)
    fig.text(0.5, 0.01, note, ha="center", fontsize=8.5, style="italic", wrap=True)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(path, dpi=200)
    plt.close(fig)


# ----------------------------------------------------------------------------
# Markdown table (single source of truth for README numbers)
# ----------------------------------------------------------------------------
def build_markdown(res):
    ov, w = res["overall_test"], res["windows"]
    s6, s8 = res["sku_6_90_test"], res["sku_8_90_test"]
    cq = res["copq_normalized"]
    verdict = ("Significant" if ov["laney_adjusted"]["p_value"] < 0.05 and ov["batch_level"]["ci_excludes_zero"]
               else "NOT significant after overdispersion adjustment")

    def sku_row(name, t):
        v = "Significant (CI excludes 0)" if t["robust_significant"] else "Not significant (CI includes 0)"
        bl = t["batch_level"]
        return (f'| {name} reject rate | {t["pre_reject_rate"]:.2%} ({bl["n_batches_pre"]} batches) '
                f'| {t["post_reject_rate"]:.2%} ({bl["n_batches_post"]} batches) | {t["delta_pct"]:+.1f}% '
                f'| Naive Z={t["z_score_naive"]:.2f}; Mann-Whitney p={bl["mannwhitney_p"]:.3f}; '
                f'bootstrap 95% CI of drop [{bl["boot_ci_diff_pp"][0]:+.2f}, {bl["boot_ci_diff_pp"][1]:+.2f}] pp -> **{v}** |')

    lines = [
        "| Metric | Baseline | Post | Change | Evidence |",
        "|---|---|---|---|---|",
        f'| Window | {w["pre"]["first"]} to {w["pre"]["last"]} ({w["pre"]["months_with_data"]} of '
        f'{w["pre"]["months_span"]} months have data) | {w["post"]["first"]} to {w["post"]["last"]} '
        f'({w["post"]["months_with_data"]} of {w["post"]["months_span"]} months have data) | - | - |',
        f'| Batches / pieces | {w["pre"]["batches"]} / {w["pre"]["pcs"]:,} | {w["post"]["batches"]} / '
        f'{w["post"]["pcs"]:,} | - | - |',
        f'| Overall reject rate (pooled) | {ov["pre_reject_rate"]:.2%} | {ov["post_reject_rate"]:.2%} '
        f'| {ov["delta_pct"]:+.1f}% | Naive Z={ov["z_score_naive"]:.2f} (p={ov["p_value_naive"]:.4f}); '
        f'Laney-adjusted Z={ov["laney_adjusted"]["z"]:.2f} (p={ov["laney_adjusted"]["p_value"]:.2f}); '
        f'95% CI of drop [{ov["laney_adjusted"]["ci_diff_pp"][0]:+.2f}, {ov["laney_adjusted"]["ci_diff_pp"][1]:+.2f}] pp; '
        f'batch-level Mann-Whitney p={ov["batch_level"]["mannwhitney_p"]:.3f} -> **{verdict}** |',
        f'| Average batch reject rate | {ov["pre_avg_batch_rate"]:.2%} | {ov["post_avg_batch_rate"]:.2%} | - | unweighted mean of batches |',
        sku_row('6" 90', s6),
        sku_row('8" 90', s8),
        f'| Scrap cost per piece produced (assumed Rp {cq["unit_cost_idr"]:,}/pc) '
        f'| Rp {cq["pre_cost_per_pc_produced"]:,.0f} | Rp {cq["post_cost_per_pc_produced"]:,.0f} '
        f'| {cq["change_pct"]:+.1f}% | assumption-based, not measured |',
    ]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def _default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    raise TypeError(type(o))


def run(base="."):
    df, s, proc = load(base)
    dash = os.path.join(base, "dashboard")
    os.makedirs(dash, exist_ok=True)

    # --- limits per phase -----------------------------------------------------
    df["run_rule"] = False
    sig = {}
    for ph in (PRE, POST):
        m = df.phase == ph
        lim, sz = laney_limits(df.loc[m])
        for c in lim.columns:
            df.loc[m, c] = lim[c]
        df.loc[m, "sigma_z"] = sz
        sig[ph] = sz
        df.loc[m, "run_rule"] = run_flags(df.loc[m, "p"], float(lim.p_bar.iloc[0]))
    df["ooc_laney"] = df.p > df.ucl_laney
    df["ooc_std"] = df.p > df.ucl_std
    df["below_lcl_laney"] = (df.p < df.lcl_laney) & (df.lcl_laney > 0)
    g = df.groupby("phase")
    df["rolling_p5"] = (g["reject_pcs"].transform(lambda x: x.rolling(ROLL_N, min_periods=3).sum())
                        / g["total_pcs"].transform(lambda x: x.rolling(ROLL_N, min_periods=3).sum()))

    pre, post = df[df.phase == PRE], df[df.phase == POST]
    x1, n1, x2, n2 = pre.reject_pcs.sum(), pre.total_pcs.sum(), post.reject_pcs.sum(), post.total_pcs.sum()

    # --- overall test -----------------------------------------------------------
    t = two_prop(x1, n1, x2, n2)
    sz_used = float(np.mean([sig[PRE], sig[POST]]))
    z_adj = t["z"] / sz_used
    overall = {
        "pre_reject_rate": t["p1"], "post_reject_rate": t["p2"],
        "delta_pct": (t["p2"] - t["p1"]) / t["p1"] * 100,
        "pre_avg_batch_rate": float(pre.p.mean()), "post_avg_batch_rate": float(post.p.mean()),
        "z_score_naive": t["z"], "p_value_naive": t["p"],
        "statistically_significant": bool(t["p"] < 0.05),    # naive - kept for backward compatibility
        "laney_adjusted": {
            "sigma_z_used": sz_used, "z": z_adj,
            "p_value": float(2 * (1 - stats.norm.cdf(abs(z_adj)))),
            "ci_diff_pp": [float((t["diff"] - 1.96 * t["se"] * sz_used) * 100),
                           float((t["diff"] + 1.96 * t["se"] * sz_used) * 100)],
            "method": "pooled-SE two-proportion CI, SE inflated by mean phase sigma_z",
        },
        "batch_level": batch_level(pre, post),
    }

    sens = sigma_z_sensitivity(df)
    best_sz = float(np.mean([sens[PRE][0], sens[POST][0]]))          # lowest plausible sigma_z
    z_best = t["z"] / best_sz
    overall["laney_adjusted"]["sigma_z_range_within_day_order"] = sens
    overall["laney_adjusted"]["p_value_most_favorable"] = float(2 * (1 - stats.norm.cdf(abs(z_best))))

    # --- windows ----------------------------------------------------------------
    def window(sub):
        span = pd.period_range(sub.date.min(), sub.date.max(), freq="M")
        have = sub.date.dt.to_period("M").nunique()
        return {"first": f"{sub.date.min():%Y-%m-%d}", "last": f"{sub.date.max():%Y-%m-%d}",
                "batches": int(len(sub)), "pcs": int(sub.total_pcs.sum()),
                "months_span": int(len(span)), "months_with_data": int(have)}

    windows = {"pre": window(pre), "post": window(post)}

    # --- density capability ---------------------------------------------------------
    caps = {}
    for ph in (PRE, POST):
        ids = set(df[df.phase == ph].batch_id)
        caps[ph] = capability(s[s.batch_id.isin(ids)].density_kgm3)

    # --- COPQ -------------------------------------------------------------------------
    pre_c, post_c = x1 * UNIT_COST_IDR / n1, x2 * UNIT_COST_IDR / n2
    copq = {"unit_cost_idr": UNIT_COST_IDR, "unit_cost_is_assumption": True,
            "pre_total_idr": int(x1 * UNIT_COST_IDR), "post_total_idr": int(x2 * UNIT_COST_IDR),
            "pre_cost_per_pc_produced": float(pre_c), "post_cost_per_pc_produced": float(post_c),
            "saving_per_pc_produced": float(pre_c - post_c),
            "change_pct": float((post_c - pre_c) / pre_c * 100)}

    # --- alarms -----------------------------------------------------------------------
    alarms = [{"batch_id": r.batch_id, "date": r.date, "size": r["size"], "total_pcs": int(r.total_pcs),
               "reject_pcs": int(r.reject_pcs), "reject_rate": float(r.p),
               "defect_category": None if pd.isna(r.defect_category) else r.defect_category}
              for _, r in df[df.ooc_laney].iterrows()]

    monthly = monthly_table(df, sz_used)

    result = {
        "overall_test": overall,
        "sku_6_90_test": sku_test(df, '6" 90'),
        "sku_8_90_test": sku_test(df, '8" 90'),
        "windows": windows,
        "copq_normalized": copq,
        "density_capability": {"pre_intervention": caps[PRE], "post_intervention": caps[POST]},
        "spc_laney_parameters": {
            "sigma_z_pre": sig[PRE], "sigma_z_post": sig[POST],
            "pre_center_line": float(pre.p_bar.iloc[0]), "post_center_line": float(post.p_bar.iloc[0]),
            "standard_ooc_pre": int(pre.ooc_std.sum()), "standard_ooc_post": int(post.ooc_std.sum()),
            "laney_ooc_pre": int(pre.ooc_laney.sum()), "laney_ooc_post": int(post.ooc_laney.sum()),
            "below_lcl_laney_total": int(df.below_lcl_laney.sum()),
            "run_rule_signals_pre": int(pre.run_rule.sum()), "run_rule_signals_post": int(post.run_rule.sum()),
            "run_rule_length": RUN_LEN, "rolling_window": ROLL_N,
            "laney_alarms": alarms,
        },
        "monthly": monthly,
    }
    with open(os.path.join(proc, "statistical_evaluation_summary.json"), "w") as f:
        json.dump(result, f, indent=2, default=_default)
    with open(os.path.join(proc, "results_table.md"), "w") as f:
        f.write(build_markdown(result))

    pooled = {PRE: t["p1"], POST: t["p2"]}
    chart_overview(df, sig, os.path.join(dash, "pipe_cover_laney_spc_chart.png"))
    chart_by_sku(df, os.path.join(dash, "pipe_cover_laney_by_sku.png"))
    chart_monthly(monthly, sz_used, pooled, os.path.join(dash, "pipe_cover_monthly_trend.png"))
    chart_density(df, s, caps, os.path.join(dash, "pipe_cover_density_capability.png"))
    chart_pareto(df, float(s.density_kgm3.max()), os.path.join(dash, "pipe_cover_pareto_anonymized.png"))

    print("Charts: pipe_cover_laney_spc_chart / laney_by_sku / monthly_trend / density_capability / pareto_anonymized")
    print(f"Overall: {t['p1']:.2%} -> {t['p2']:.2%} | naive Z={t['z']:.2f} | Laney-adjusted Z={z_adj:.2f} "
          f"(p={overall['laney_adjusted']['p_value']:.2f})")
    print(f"Laney alarms: {len(alarms)} | run-rule signals: pre={int(pre.run_rule.sum())}, post={int(post.run_rule.sum())}")
    return result


if __name__ == "__main__":
    run(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
