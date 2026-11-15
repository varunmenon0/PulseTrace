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


def test_contact_peak_times_recover_known_pulse_train(tmp_path):
    t=np.arange(0,25,1/60)
    beats=np.arange(.5,25,.8)
    wave=sum(np.exp(-.5*((t-beat)/.055)**2) for beat in beats)
    p=tmp_path/'reference.txt';np.savetxt(p,[wave,np.full(len(t),75.),t])
    w=audit(p)['windows'][0]
    detected=np.array(w['detected_peak_times_s'])
    assert len(detected)>=10
    assert max(min(abs(beat-detected)) for beat in beats if 1.2<beat<10.8)<.07
    assert np.allclose(w['interbeat_intervals_s'],np.diff(detected))
    assert abs(w['ppg_interbeat_bpm']-75)<1


def test_contact_audit_does_not_bridge_a_reference_gap(tmp_path):
    t=np.arange(0,25,1/30);t=t[(t<4)|(t>8)]
    p=tmp_path/'reference.txt'
    np.savetxt(p,[np.sin(2*np.pi*t),np.full(len(t),60.),t])
    w=audit(p)['windows'][0]
    assert w['warning']=='Reference gap'
    assert 'detected_peak_times_s' not in w
