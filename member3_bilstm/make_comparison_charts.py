"""Bar charts for the report: reads reports/comparison_metrics.json, writes PNGs to reports/."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out = Path("reports")
res = json.loads((out / "comparison_metrics.json").read_text())
models = ["Persistence", "Ridge (linear)", "Gradient Boosting", "LSTM", "Bi-LSTM (ours)"]
labels = ["Persistence\n(last hour)", "Ridge\n(linear)", "Gradient\nBoosting", "LSTM\n(one direction)", "Bi-LSTM\n(ours)"]
GREY, NAVY, TEAL = "#9AA5B1", "#1F3A5F", "#2A9D8F"
colors = ["#C9CFD6", "#9AA5B1", "#6B7785", "#6C8EBF", TEAL]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

def bars(ax, vals, title, ylabel, fmt="{:.1f}", lower_better=True, ylim=None):
    b = ax.bar(range(len(vals)), vals, color=colors, width=0.62)
    for r, v in zip(b, vals):
        ax.text(r.get_x() + r.get_width() / 2, v + (0.012 * (ax.get_ylim()[1] if ylim is None else ylim[1])) if v >= 0 else v - 0.02,
                fmt.format(v), ha="center", va="bottom" if v >= 0 else "top", fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(vals))); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_title(title, fontsize=11, fontweight="bold", color=NAVY); ax.set_ylabel(ylabel)
    if ylim: ax.set_ylim(*ylim)
    ax.grid(axis="y", alpha=0.25)

# Figure 1: MAE and RMSE
mae = [res[m]["overall"]["MAE"] for m in models]; rmse = [res[m]["overall"]["RMSE"] for m in models]
fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
bars(ax[0], mae, "Test MAE (lower is better)", "AQI points", ylim=(0, 66))
bars(ax[1], rmse, "Test RMSE (lower is better)", "AQI points", ylim=(0, 84))
fig.suptitle("Next-hour AQI forecast: error comparison on the test period (13 Sep - 31 Dec 2023)", fontsize=12)
fig.tight_layout(); fig.savefig(out / "fig1_mae_rmse_comparison.png", dpi=200); plt.close(fig)

# Figure 2: R2
r2 = [res[m]["overall"]["R2"] for m in models]
fig, ax = plt.subplots(figsize=(7.5, 4.4))
bars(ax, r2, "Test R-squared (higher is better)", "R-squared", fmt="{:.3f}", ylim=(-0.32, 0.5))
ax.axhline(0, color="black", lw=0.8)
fig.tight_layout(); fig.savefig(out / "fig2_r2_comparison.png", dpi=200); plt.close(fig)

# Figure 3: per-city MAE
cities = ["Delhi", "Faridabad", "Gurugram"]
fig, ax = plt.subplots(figsize=(10, 4.4)); w = 0.16; x = np.arange(len(cities))
for i, (m, lab, c) in enumerate(zip(models, [l.replace("\n", " ") for l in labels], colors)):
    vals = [res[m][ct]["MAE"] for ct in cities]
    b = ax.bar(x + (i - 2) * w, vals, w, label=lab, color=c)
    for r, v in zip(b, vals): ax.text(r.get_x() + r.get_width() / 2, v + 0.6, f"{v:.1f}", ha="center", fontsize=7.5)
ax.set_xticks(x); ax.set_xticklabels(cities); ax.set_ylabel("MAE (AQI points)"); ax.set_ylim(0, 66)
ax.set_title("Test MAE by city (lower is better)", fontsize=11, fontweight="bold", color=NAVY)
ax.legend(ncol=5, fontsize=8, loc="upper center", frameon=False); ax.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(out / "fig3_mae_by_city.png", dpi=200); plt.close(fig)
print("charts written")
