# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Diagnostic plot: Sun/Earth elevation at the reference site (2027-01..03) and at Shackleton (2027-01)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.ephemeris import load_ephemeris, local_az_el  # noqa: E402

eph = load_ephemeris()
ref = (float(eph.meta["ref_lat"]), float(eph.meta["ref_lon"]))
start = datetime(2027, 1, 1, tzinfo=timezone.utc)
t, sun, earth = eph.window(start, 24 * 90)
x = [start + timedelta(hours=i) for i in range(len(t))]
fig, axs = plt.subplots(2, 1, figsize=(11, 7))
for ax, (lat, lon), name, n in [(axs[0], ref, "Reference site", len(t)), (axs[1], (-89.67, 129.78), "Shackleton", 24 * 31)]:
    _, se = local_az_el(sun[:n], np.array([lat]), np.array([lon]))
    _, ee = local_az_el(earth[:n], np.array([lat]), np.array([lon]))
    ax.plot(x[:n], se[0], color="#E0B000", label="Sun")
    ax.plot(x[:n], ee[0], color="#3B82F6", label="Earth")
    ax.axhline(0, color="gray", ls="--", lw=1, label="Flat horizon")
    ax.set_title(f"{name} ({lat}, {lon}) — elevation from the Moon-fixed vector table")
    ax.set_ylabel("Elevation (°)"); ax.legend(loc="upper right"); ax.grid(alpha=.3)
axs[1].set_xlabel("UTC")
fig.tight_layout()
out = ROOT / "docs" / "ephemeris_check.png"
fig.savefig(out, dpi=130)
print("saved", out)
