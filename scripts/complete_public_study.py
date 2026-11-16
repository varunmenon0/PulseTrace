"""Score a frozen public-video cohort and write a publishable aggregate summary."""
import argparse
import json
from pathlib import Path

from evaluate_real_recovery import evaluate, summarize, digest


def run(root, subjects, output, protocol):
    records=[];failures=[]
    output.mkdir(parents=True,exist_ok=True)
    for subject in subjects:
        try:
            record=evaluate(root/subject,output/subject)
            records.append(record)
            print(subject,'completed',flush=True)
        except (ValueError,OSError,KeyError) as error:
            failures.append(dict(recording=subject,error=str(error)))
            print(subject,'failed:',error,flush=True)
    report=dict(protocol=protocol,records=records,failures=failures,metrics=summarize(records))
    (output/'private-results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    metrics=summarize(records)
    for methods in metrics.values():
        for detail in methods.values():
            pairs=detail['paired'];errors=pairs.pop('newly_scorable_errors_bpm')
            pairs['newly_scorable_max_difference_bpm']=max(map(abs,errors)) if errors else None
    public=dict(planned_recordings=len(subjects),completed_recordings=len(records),failed_recordings=len(failures),
        decoded_frames=sum(r['input']['decoded_frames'] for r in records),metrics=metrics,
        frozen_estimator_commit=protocol['frozen_estimator_commit'],
        reference='Stored device labels; assumed shared elapsed-time origin; overlapping windows are dependent',
        outputs='Cohort aggregate; individual pulse outcomes stay in private-results.json')
    (output/'aggregate.json').write_text(json.dumps(public,indent=2,allow_nan=False)+'\n')
    return report,public


def select_demo(records):
    """Explicit selection for presentation, separate from fresh evaluation."""
    eligible=[]
    for record in records:
        metrics=record['metrics']['pos']['twelve_patches']['continuous']
        fraction=metrics['scorable_windows']/metrics['total_windows'] if metrics['total_windows'] else 0
        error=metrics['mae_against_device_bpm']
        if fraction>=.8 and error is not None and error<=5:
            eligible.append((fraction,error,record['recording']))
    return sorted(eligible,key=lambda r:(-r[0],r[1],r[2]))[0][2] if eligible else None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cohort',choices=['development','fresh'],required=True)
    p.add_argument('--protocol',type=Path,default=Path(__file__).resolve().parents[1]/'examples/public-demonstration/protocol.json')
    args=p.parse_args();protocol=json.loads(args.protocol.read_text())
    run(args.root,protocol[args.cohort+'_subjects'],args.output,protocol)


if __name__=='__main__':main()
