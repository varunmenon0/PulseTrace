import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from report_real_sampling import compare, aggregate


def report(errors):
    windows=[]
    for i,error in enumerate(errors):
        windows.append(dict(start_s=i*6,end_s=i*6+12,nominal_reference_bpm=72.,
            policies=dict(full=dict(methods={m:{l:dict(error_bpm=error) for l in ('three_regions','twelve_patches')}
                                              for m in ('pos','green')}))))
    return dict(failures=[],records=[dict(recording='subject',input=dict(video_sha256='video'),reference_sha256='reference',windows=windows)])


def test_cross_sampler_common_new_and_lost_windows_remain_separate():
    result=compare(report([1.,None,4.]),report([2.,3.,None]))['pos']['twelve_patches']
    assert result['common_windows']==1
    assert result['integer_common_mae']==1
    assert result['fractional_common_mae']==2
    assert result['newly_scorable'][0]['start_s']==6
    assert result['lost'][0]['start_s']==12


def test_mismatched_sources_or_failed_records_cannot_be_silently_pooled():
    a=report([1.]);b=copy.deepcopy(a);b['records'][0]['reference_sha256']='other'
    with pytest.raises(ValueError):compare(a,b)
    b=copy.deepcopy(a);b['failures']=[dict(recording='failed')]
    with pytest.raises(ValueError):compare(a,b)


def test_public_summary_keeps_aggregate_counts_without_record_identifiers():
    metrics={m:{l:dict(paired=dict(newly_scorable_errors_bpm=[3.])) for l in ('three_regions','twelve_patches')}
             for m in ('pos','green')}
    source=dict(paired=compare(report([1.,None]),report([2.,3.])),
        quality_events=dict(integer=dict(private_record=dict(raw_flagged_frames=dict(displacement=0,patch_area=3,missing=0)))),
        integer_metrics=metrics,fractional_metrics=metrics)
    result=aggregate(source)
    assert result['paired']['pos']['twelve_patches']['newly_scorable_windows']==1
    assert result['paired']['pos']['twelve_patches']['newly_scorable_mae']==3
    assert result['quality_events']['integer']['raw_flagged_frames']['patch_area']==3
    assert 'private_record' not in str(result)
    assert 'newly_scorable_errors_bpm' not in str(result)
    assert 'private_record' in str(source)
