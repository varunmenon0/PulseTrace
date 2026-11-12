import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from audit_contact_reference import audit


def test_contact_audit_reports_disagreement_without_video_input(tmp_path):
    t=np.arange(0,25,1/30);wave=np.sin(2*np.pi*1.2*t)
    p=tmp_path/'reference.txt';np.savetxt(p,[wave,np.full(len(t),98.),t])
    r=audit(p);w=r['windows'][0]
    assert abs(w['ppg_spectral_bpm']-72)<1
    assert abs(w['ppg_interbeat_bpm']-72)<1
    assert w['device_ppg_disagreement_over_10_bpm']
    assert not w['ppg_methods_disagree_over_6_bpm']
