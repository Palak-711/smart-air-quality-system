"""Charts comparing with the two GitHub projects. Reads JSONs in reports/, writes fig4/fig5 PNGs."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = Path("reports")
ours = json.loads((R / "comparison_metrics.json").read_text())
fc = json.loads((R / "existing_forecast_protocol.json").read_text())
nc = json.loads((R / "existing_nowcast_protocol.json").read_text())
rep = json.loads((R / "okes_reproduced_metrics.json").read_text())
NAVY, TEAL = "#1F3A5F", "#2A9D8F"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

# ---- Fig 4: like-for-like (our task, our data, our time-ordered split)
names = ["Persistence", "Ridge\n(Okes)", "Random\nForest\n(Okes)", "Gradient\nBoosting\n(Okes)", "LSTM", "Bi-LSTM\n(ours)"]
src = [ours["Persistence"]["overall"], fc["Ridge"], fc["RandomForest"], fc["GradientBoosting"], ours["LSTM"]["overall"], ours["Bi-LSTM (ours)"]["overall"]]
cols = ["#C9CFD6", "#E3A857", "#E3A857", "#E3A857", "#6C8EBF", TEAL]
fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
for a, key, title, fmt, yl in [(ax[0], "MAE", "Test MAE (lower is better)", "{:.1f}", (0, 66)),
                               (ax[1], "RMSE", "Test RMSE (lower is better)", "{:.1f}", (0, 84)),
                               (ax[2], "R2", "Test R-squared (higher is better)", "{:.3f}", (-0.32, 0.5))]:
    v = [s[key] for s in src]
    b = a.bar(range(6), v, color=cols, width=0.65)
    for r, x in zip(b, v):
        a.text(r.get_x() + r.get_width() / 2, x + (0.01 * yl[1] if x >= 0 else -0.015), fmt.format(x), ha="center",
               va="bottom" if x >= 0 else "top", fontsize=8.5, fontweight="bold")
    a.set_xticks(range(6)); a.set_xticklabels(names, fontsize=8); a.set_ylim(*yl)
    a.set_title(title, fontsize=10.5, fontweight="bold", color=NAVY); a.grid(axis="y", alpha=0.25)
    if key == "R2": a.axhline(0, color="black", lw=0.8)
fig.suptitle("Same task and data for every model: next-hour AQI forecast, time-ordered test (13 Sep - 31 Dec 2023)\n"
             "Orange = model types used by github.com/Okes2024/Air-Quality-Index-Prediction..., re-trained under our protocol", fontsize=11)
fig.tight_layout(); fig.savefig(R / "fig4_like_for_like_vs_existing.png", dpi=200); plt.close(fig)

# ---- Fig 5: why headline numbers are not comparable (R-squared only: AQI scales differ, EPA vs CPCB)
fam = ["Ridge", "RandomForest", "GradientBoosting"]; fam_lab = ["Ridge", "Random Forest", "Gradient Boosting"]
A = [rep[f]["R2"] for f in fam]            # their repo as reproduced: synthetic data, same-hour AQI, random split
B = [nc[f]["R2"] for f in fam]             # their task on OUR data
C = [fc[f]["R2"] for f in fam]             # our task (1-h forecast) with their models
x = np.arange(3); w = 0.25
fig, ax = plt.subplots(figsize=(10.5, 5))
sets = [(A, "Their repo as reproduced\n(synthetic data, same-hour AQI, random split)", "#9AA5B1"),
        (B, "Their task on OUR data\n(same-hour AQI, random split)", "#E3A857"),
        (C, "Our task\n(real data, 1-hour-ahead forecast, time-ordered split)", TEAL)]
for i, (vals, lab, c) in enumerate(sets):
    bars = ax.bar(x + (i - 1) * w, vals, w, label=lab, color=c)
    for r, v in zip(bars, vals): ax.text(r.get_x() + r.get_width() / 2, v + 0.015, f"{v:.3f}", ha="center", fontsize=8.5, fontweight="bold")
bl = ours["Bi-LSTM (ours)"]["overall"]["R2"]
ax.bar(3 + w, bl, w, color="#146B5F", label="Bi-LSTM (ours), our task")
ax.text(3 + w, bl + 0.015, f"{bl:.3f}", ha="center", fontsize=8.5, fontweight="bold")
ax.set_xticks(list(x) + [3 + w / 2 + 0.0]); ax.set_xticklabels(fam_lab + ["Bi-LSTM"])
ax.set_ylabel("Test R-squared"); ax.set_ylim(0, 1.18); ax.axhline(1, color="grey", lw=0.6, ls=":")
ax.set_title("High R-squared in the other repo comes from the task, not from forecasting skill", fontsize=11.5, fontweight="bold", color=NAVY)
ax.legend(fontsize=8, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.12)); ax.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(R / "fig5_task_difference_vs_existing.png", dpi=200); plt.close(fig)
print("ok")
