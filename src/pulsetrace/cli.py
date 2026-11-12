"""Command line demo and real-video analysis."""
import argparse
import json
import importlib.metadata
from pathlib import Path
from .pipeline import extract_video, analyze_extraction
from .report import write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="PulseTrace: estimate heart rate from facial video using rPPG")
    sub = parser.add_subparsers(dest="command", required=True)
    real = sub.add_parser("analyze", help="Analyze a single-person video with MediaPipe")
    real.add_argument("video", type=Path)
    real.add_argument("--model", type=Path, required=True)
    real.add_argument("--max-seconds", type=float)
    real.add_argument("--regional-quality", action="store_true", help="Write experimental local-region versus global quality comparison")
    real.add_argument("--sampling", choices=["landmarks", "template"], default="landmarks")
    real.add_argument("--overlay", action="store_true", help="Write annotated tracking.avi (contains face video)")
    demo = sub.add_parser("demo", help="Synthetic video integration demo; no model required")
    demo.add_argument("--bpm", type=float, default=72)
    demo.add_argument("--seconds", type=float, default=20)
    for cmd in (real, demo):
        cmd.add_argument("--patches", action="store_true", help="Compare 12 patches with three parent regions")
        cmd.add_argument("--output", type=Path, default=Path("outputs/run"))
        cmd.add_argument("--method", choices=["green", "pos"], default="pos")
        cmd.add_argument("--min-seconds", type=float, default=10)
        cmd.add_argument("--max-gap", type=float, default=.25)
    diagnostic = sub.add_parser("diagnose", help="Inspect existing RGB CSV; no video/model needed")
    diagnostic.add_argument("rgb_csv", type=Path)
    diagnostic.add_argument("--output", type=Path, default=Path("outputs/diagnostics"))
    diagnostic.add_argument("--window-seconds", type=float, default=12)
    diagnostic.add_argument("--step-seconds", type=float, default=6)
    evaluate = sub.add_parser("evaluate", help="Compare RGB windows with synchronized reference BPM CSV")
    evaluate.add_argument("rgb_csv", type=Path)
    evaluate.add_argument("reference_csv", type=Path)
    evaluate.add_argument("--reference-offset", type=float, required=True,
                          help="reference time = video time + this offset (seconds)")
    evaluate.add_argument("--output", type=Path, default=Path("outputs/evaluation"))
    segments = sub.add_parser("segments", help="Exclude motion/area spikes and analyze separate usable sections")
    segments.add_argument("rgb_csv", type=Path)
    segments.add_argument("--output", type=Path, default=Path("outputs/segments"))
    segments.add_argument("--min-seconds", type=float, default=10.)
    segments.add_argument("--buffer-seconds", type=float, default=.5)
    args = parser.parse_args(argv)
    if args.command == "analyze" and args.regional_quality and not args.patches:
        parser.error("--regional-quality requires --patches for the layout comparison")
    try:
        if args.command == "segments":
            from .diagnostics import load_rgb_csv
            from .quality import write_segments
            report = write_segments(load_rgb_csv(args.rgb_csv), args.output,
                                    min_seconds=args.min_seconds, buffer_seconds=args.buffer_seconds)
            print(json.dumps(report, indent=2))
            return 0 if report["status"] == "segments_available" else 2
        if args.command == "evaluate":
            from .diagnostics import load_rgb_csv
            from .evaluation import evaluate_csv
            result = evaluate_csv(load_rgb_csv(args.rgb_csv), args.reference_csv, args.output,
                                  reference_offset=args.reference_offset)
            print(json.dumps({"output":str(args.output.resolve()),
                              "metrics":{n:{m:{k:v for k,v in d.items() if k!="windows"}
                                            for m,d in methods.items()} for n,methods in result["regions"].items()}},indent=2))
            return 0
        if args.command == "diagnose":
            from .diagnostics import load_rgb_csv, write_diagnostics
            report = write_diagnostics(load_rgb_csv(args.rgb_csv), args.output,
                                       window_seconds=args.window_seconds, step_seconds=args.step_seconds)
            print(json.dumps({"output": str(args.output.resolve()),
                              "motion_available": all(r["motion_available"] for r in report["regions"].values()),
                              "note": "Diagnostics only; no authenticity or validated pulse verdict"},indent=2))
            return 0
        if args.command == "demo":
            from .synthetic import make_video, SyntheticTracker
            args.output.mkdir(parents=True, exist_ok=True)
            video = args.output / "synthetic.avi"
            make_video(video, bpm=args.bpm, seconds=args.seconds)
            extraction = extract_video(video, SyntheticTracker(), patches=args.patches)
            extraction.metadata.update({"synthetic": True, "expected_bpm": args.bpm,
                                         "tracking": "known fixture geometry; not MediaPipe"})
        else:
            from .tracking import FaceTracker
            with FaceTracker(args.model) as tracker:
                extraction = extract_video(args.video, tracker, max_seconds=args.max_seconds, sampling=args.sampling,
                                           overlay_path=args.output/"tracking.avi" if args.overlay else None, patches=args.patches)
            extraction.metadata["synthetic"] = False
            extraction.metadata["tracking"] = "MediaPipe Face Landmarker VIDEO"
        results, failures = analyze_extraction(extraction, method=args.method,
                                               min_seconds=args.min_seconds, max_gap=args.max_gap)
        extraction.metadata["configuration"] = {
            "min_seconds": args.min_seconds, "max_gap_s": args.max_gap,
            "band_bpm": [40, 200], "pos_window_s": 1.6,
            "filter_order": 4, "spectral_peak_fraction_cutoff": .35,
        }
        extraction.metadata["versions"] = {
            name: importlib.metadata.version(name)
            for name in ("pulsetrace", "numpy", "scipy", "opencv-contrib-python", "mediapipe", "matplotlib")
        }
        summary = write_report(extraction, results, failures, args.output, args.method)
        print(json.dumps({"output": str(args.output.resolve()), "regions": summary["regions"],
                          "failures": failures}, indent=2))
        from .diagnostics import write_diagnostics
        write_diagnostics(extraction, args.output, max_gap=args.max_gap)
        from .quality import write_segments
        segments = write_segments(extraction, args.output, min_seconds=args.min_seconds, max_gap=args.max_gap)
        if args.command == "analyze" and args.regional_quality:
            from .regional_quality import write_regional_comparison
            write_regional_comparison(extraction,args.output)
        if args.patches:
            from .patches import write_patch_comparison
            comparison = write_patch_comparison(extraction, segments, args.output)
            return 0 if any(row[method]["patch_consensus"]["bpm_candidate"] is not None
                            for row in comparison["segments"] for method in ("green", "pos")) else 2
        return 0 if results and any(r.bpm is not None for r in results.values()) else 2
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"pulsetrace: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
