"""Pool global/regional gate results, keeping failures in coverage denominators."""
import argparse
import json
from pathlib import Path
import numpy as np


def summarize(reports):
    summary={"recordings":len(reports),"metrics":{}}
    for method in ("pos","green"):
        summary["metrics"][method]={}
        for layout in ("three_regions","twelve_patches"):
            metrics={};rows=[w for report in reports for w in report["windows"] if w["reference_bpm"] is not None]
            for gate in ("global_gate","regional_gate"):
                errors=[w["methods"][method][layout][gate]["error_bpm"] for w in rows
                        if w["methods"][method][layout][gate]["error_bpm"] is not None]
                metrics[gate]={"reference_valid_windows":len(rows),"accepted_windows":len(errors),
                               "coverage":len(errors)/len(rows) if rows else 0.,
                               "mae_bpm":float(np.mean(np.abs(errors))) if errors else None}
            new=[];lost=[]
            for w in rows:
                g=w["methods"][method][layout]["global_gate"]["error_bpm"]
                r=w["methods"][method][layout]["regional_gate"]["error_bpm"]
                if g is None and r is not None:new.append(r)
                if g is not None and r is None:lost.append(g)
            metrics["newly_admitted"]={"windows":len(new),"mae_bpm":float(np.mean(np.abs(new))) if new else None,
                                      "max_absolute_error_bpm":float(np.max(np.abs(new))) if new else None}
            metrics["lost_global_estimates"]=len(lost)
            summary["metrics"][method][layout]=metrics
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("reports",type=Path,nargs="+");p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    reports=[json.loads(path.read_text()) for path in args.reports]
    result=summarize(reports)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
