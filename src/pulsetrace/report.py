"""Headless CSV, JSON, waveform/PSD plots, and ROI preview exports."""
import csv
import json
from pathlib import Path
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .regions import REGIONS
from .diagnostics import GEOMETRY_COLUMNS


def write_report(extraction, results, failures, output, method):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = list(REGIONS)
    # A repeated run must not leave previous successful outputs beside new failures.
    for name in names:
        for suffix in ("pulse", "spectrum"):
            (output / f"{name}_{suffix}.csv").unlink(missing_ok=True)
    (output / "regions.png").unlink(missing_ok=True)
    with (output / "rgb.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["time_s"] + [f"{n}_{c}" for n in names for c in ("r", "g", "b", "pixels")] +
                        [f"{n}_{c}" for n in names if n in extraction.geometry for c in GEOMETRY_COLUMNS])
        for i,t in enumerate(extraction.time):
            writer.writerow([t] + [value for n in names for value in
                                   (*extraction.rgb[n][i], extraction.pixels[n][i])] +
                            [v for n in names if n in extraction.geometry for v in extraction.geometry[n][i]])
    summary = {"phase": "signal_extraction_only", "method": method,
               "metadata": extraction.metadata, "failures": failures, "regions": {}}
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), constrained_layout=True)
    for row, name in enumerate(names):
        result = results.get(name)
        if result is None:
            axes[row, 0].text(0.05, 0.5, failures.get(name, "No result"), transform=axes[row,0].transAxes)
        else:
            np.savetxt(output / f"{name}_pulse.csv", np.column_stack([result.time, result.pulse]),
                       delimiter=",", header="time_s,pulse", comments="")
            np.savetxt(output / f"{name}_spectrum.csv", np.column_stack([result.frequencies, result.power]),
                       delimiter=",", header="frequency_hz,power", comments="")
            axes[row,0].plot(result.time, result.pulse, linewidth=0.8)
            axes[row,1].plot(result.frequencies * 60, result.power)
            axes[row,1].set_xlim(30, 220)
            label = f"{result.bpm:.1f} BPM candidate" if result.bpm else "No usable estimate"
            axes[row,1].set_title(label)
            if result.bpm:
                axes[row,1].axvline(result.bpm, color="red", linestyle="--", alpha=0.5)
            summary["regions"][name] = {
                "bpm_candidate": result.bpm, "peak_fraction": result.peak_fraction,
                "sample_rate_hz": result.sample_rate, "segment_duration_s": result.duration,
                "interpolated_fraction": result.interpolated_fraction,
                "valid_frame_fraction": float(np.mean(extraction.pixels[name] > 0)),
                "warnings": result.warnings,
            }
        axes[row,0].set_title(name)
        axes[row,0].set_xlabel("Time (s)")
        axes[row,0].set_ylabel("Relative pulse amplitude")
        axes[row,1].set_xlabel("Frequency (BPM)")
        axes[row,1].set_ylabel("Power density")
    fig.suptitle(f"PulseTrace · {method.upper()} · signal extraction only")
    fig.savefig(output / "waveforms.png", dpi=150)
    plt.close(fig)
    if extraction.preview is not None:
        image = extraction.preview.copy()
        colors = [(0, 220, 255), (255, 180, 0), (180, 0, 255)]
        overlay = image.copy()
        for (name, mask), color in zip(extraction.masks.items(), colors):
            overlay[mask > 0] = color
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image, contours, -1, color, 1)
            x,y,w,h = cv2.boundingRect(mask)
            cv2.putText(image, name, (x,max(12,y-4)), cv2.FONT_HERSHEY_SIMPLEX, .35, color, 1)
        if not cv2.imwrite(str(output / "regions.png"), cv2.addWeighted(image, .7, overlay, .3, 0)):
            raise OSError("Cannot write ROI preview")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary
