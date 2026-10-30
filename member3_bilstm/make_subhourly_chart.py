"""Bar chart for the 15/30-minute models (SIMULATED data). Reads reports/subhourly_metrics.json."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = Path("reports")
res = json.loads((R / "subhourly_metrics.json").read_text())["horizons"]
models = ["Persistence", "Ridge", "Interpolation (hourly Bi-LSTM)", "Bi-LSTM 15/30 (ours)", "Oracle interpolation (uses next real hour)"]
labels = ["Persistence", "Ridge", "Interpolation\n(hourly Bi-LSTM)", "Bi-LSTM 15/30\n(ours)", "Oracle\n(cheats: sees next hour)"]
cols = ["#C9CFD6", "#9AA5B1", "#6C8EBF", "#2A9D8F", "#F2D9A6"]
hz = ["15min", "30min"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.8))
for a, key, title, fmt in [(ax[0], "MAE", "MAE (lower is better)", "{:.1f}"), (ax[1], "RMSE", "RMSE (lower is better)", "{:.1f}"),
                           (ax[2], "R2", "R-squared (higher is better)", "{:.2f}")]:
    w = 0.16; x = np.arange(2)
    for i, (m, lab, c) in enumerate(zip(models, labels, cols)):
        vals = [res[h][m]["overall"][key] for h in hz]
        b = a.bar(x + (i - 2) * w, vals, w, color=c, label=lab.replace("\n", " "), hatch="//" if i == 4 else None, edgecolor="white")
        for r, v in zip(b, vals): a.text(r.get_x() + r.get_width() / 2, v * 1.01 + (0.004 if key == "R2" else 0.3), fmt.format(v), ha="center", fontsize=7, rotation=90 if key != "R2" else 0, va="bottom")
    a.set_xticks(x); a.set_xticklabels(["15 minutes ahead", "30 minutes ahead"]); a.set_title(title, fontsize=10.5, fontweight="bold", color="#1F3A5F"); a.grid(axis="y", alpha=0.25)
    if key == "R2": a.set_ylim(0, 1.05)
    else: a.set_ylim(0, a.get_ylim()[1] * 1.18)
ax[0].legend(fontsize=7.5, frameon=False, loc="upper left")
fig.suptitle("15- and 30-minute forecasts on SIMULATED 15-minute data (test: 13 Sep - 31 Dec 2023, forecasts issued at the top of each hour)", fontsize=11.5)
fig.tight_layout(); fig.savefig(R / "fig6_15_30min_simulated.png", dpi=200); print("ok")
