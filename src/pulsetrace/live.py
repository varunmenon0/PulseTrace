"""Recorded streaming replay, optional batch audit, and local webcam runner."""
from contextlib import contextmanager
import json
from pathlib import Path
import queue
import time

import cv2
import numpy as np

from .sampling import FrameSampler, samples_to_extraction
from .streaming import PulseStream
from .sample_archive import SampleWriter, SampleReader, provenance
from .agreement import METHOD_AGREEMENT_TOLERANCE_BPM


@contextmanager
def event_log(output, metadata):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output/'stream.jsonl').open('w') as file:
        def emit(value):
            file.write(json.dumps(value, allow_nan=False)+'\n')
            file.flush()
        emit(dict(type='session', **metadata))
        yield emit


def configuration(engine):
    return dict(method=engine.method, consensus=engine.consensus,
                window_policy=engine.window_policy, window_seconds=engine.window_seconds,
                step_seconds=engine.step_seconds, lookahead_seconds=engine.lookahead_seconds,
                max_gap_seconds=engine.max_gap, max_buffer_samples=engine.max_samples,
                quality_diagnostics_version=1,
                patch_diagnostics_version=1,
                agreement_policy=engine.agreement_policy,
                agreement_tolerance_bpm=METHOD_AGREEMENT_TOLERANCE_BPM,
                threshold_status='Unvalidated engineering heuristics')


def verify_batch(groups, readings, engine):
    """Compare identical samples and finalized windows; reference labels never enter."""
    from .regional_quality import build_regional_comparison

    checked = 0
    pending = 0
    for session, samples in groups.items():
        if len(samples) < 2:
            continue
        extraction = samples_to_extraction(samples)
        report = build_regional_comparison(extraction, consensus_policy=engine.consensus,
                                          window_policy=engine.window_policy)
        actual = [r for r in readings if r.session == session]
        eligible = [w for w in report['windows'] if w['end_s']+.5 <= samples[-1].time+1e-9]
        pending += len(report['windows'])-len(eligible)
        if len(actual) != len(eligible):
            raise ValueError('Streaming/batch finalized-window counts differ')
        for reading, row in zip(actual, eligible):
            expected = row['methods'][engine.method]['twelve_patches']['regional_gate']
            bpm = expected['bpm_candidate']
            equal = (bpm is None and reading.bpm is None) or (bpm is not None and reading.bpm is not None
                                                                           and abs(bpm-reading.bpm) < 1e-8)
            support = extraction.time[(extraction.time >= row['start_s']) & (extraction.time < row['end_s'])]
            begin, end = (float(support[0]), float(support[-1])) if len(support) else (None, None)
            if (not equal or reading.start_s != row['start_s'] or tuple(expected['support']) != reading.support
                    or reading.analysis_start_s != row.get('analysis_start_s', begin)
                    or reading.analysis_end_s != row.get('analysis_end_s', end)):
                raise ValueError('Streaming/batch estimates, support or intervals differ')
            checked += 1
    return dict(passed=True, compared_windows=checked, unfinalized_batch_windows=pending,
                scope='Raw estimator decisions and selected support; presentation flags are separate',
                note='Same tracked samples; parity is not physiological validation or a throughput benchmark')


def replay(video, tracker, output, *, sampling='fractional', method='pos', consensus='patch',
           window_policy='continuous', verify=False, synthetic=False, agreement_policy='off'):
    from .video import VideoReader

    sampler = FrameSampler(sampling=sampling)
    engine = PulseStream(method=method, consensus=consensus, window_policy=window_policy,
                         agreement_policy=agreement_policy)
    groups, readings = {}, []  # Populated only by the explicitly requested full-session audit.
    frames = 0
    last_state = None
    started = time.perf_counter()
    metadata = dict(mode='recorded_streaming_replay', synthetic=synthetic,
            sampling=sampling, audit_retains_full_session=verify, configuration=configuration(engine),
            rgb_samples_saved=True, samples_file='samples.jsonl', frames_saved=False,
            timing='Decoded source timestamps; unpaced replay; EOF does not finalize incomplete look-ahead')
    with event_log(output, metadata) as emit, SampleWriter(Path(output)/'samples.jsonl', metadata) as archive:
        with VideoReader(video) as reader:
            for frame in reader:
                points = tracker.detect(frame.bgr, frame.time)
                if synthetic and hasattr(tracker, 'background_rgb'):
                    tracker.background_rgb.clear()  # Fixture diagnostics are not needed by the streaming engine.
                sample = sampler.sample(frame.bgr, points, frame.time)
                archive.write(sample)
                new = engine.push(sample)
                frames += 1
                for reading in new:
                    emit(reading.to_dict())
                if verify:
                    groups.setdefault(engine.session, []).append(sample)
                    readings.extend(new)
                state = engine.state()
                key = (state['status'], state['session'])
                if key != last_state:
                    emit(dict(type='state', source_time_s=frame.time, **state))
                    last_state = key
        audit = verify_batch(groups, readings, engine) if verify else None
        summary = dict(type='summary', mode='recorded_streaming_replay', synthetic=synthetic,
            frames=frames, timestamp_fallbacks=reader.timestamp_fallbacks, finalized_windows=engine.finalized_windows,
            saved_samples=archive.count, samples_file='samples.jsonl',
            estimated_windows=engine.estimated_windows-engine.uncertain_windows,
            raw_estimated_windows=engine.estimated_windows, uncertain_windows=engine.uncertain_windows,
            resets=engine.resets, batch_parity=audit,
            final_state=engine.state(), processing_seconds=time.perf_counter()-started,
            incomplete_tail_policy='No EOF flush or fabricated future samples')
        emit(summary)
    (Path(output)/'stream-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary


def replay_samples(source, output, *, method=None, consensus=None, window_policy=None, verify=False,
                   agreement_policy=None):
    """Reprocess archived measurements without a camera, face model, or expected BPM."""
    import hashlib

    source, output = Path(source), Path(output)
    if output.resolve() == source.parent.resolve() or source.resolve() in {
            (output/'stream.jsonl').resolve(), (output/'stream-summary.json').resolve()}:
        raise ValueError('Replay output would overwrite its input archive')
    with source.open('rb') as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda:file.read(1024*1024), b''):
            digest.update(chunk)
    with SampleReader(source) as archive:
        metadata = archive.header['metadata']
        saved = metadata.get('configuration', {})
        if not isinstance(saved, dict) or any(saved.get(k) != expected for k,expected in (
                ('window_seconds',12),('step_seconds',6),('lookahead_seconds',.5),('max_gap_seconds',.25))):
            raise ValueError('Archived timing configuration does not match this streaming engine')
        if (agreement_policy is None and saved.get('agreement_policy') == 'flag'
                and saved.get('agreement_tolerance_bpm') != METHOD_AGREEMENT_TOLERANCE_BPM):
            raise ValueError('Archived disagreement tolerance does not match this presentation policy')
        engine = PulseStream(method=method if method is not None else saved.get('method'),
                             consensus=consensus if consensus is not None else saved.get('consensus'),
                             window_policy=window_policy if window_policy is not None else saved.get('window_policy'),
                             max_samples=saved.get('max_buffer_samples',10000),
                             agreement_policy=agreement_policy if agreement_policy is not None else
                                 saved.get('agreement_policy','off'))
        groups, readings = {}, []
        count = 0
        session = dict(mode='sample_replay', synthetic=metadata.get('synthetic',False),
                       source_sha256=digest.hexdigest(), archived_configuration=saved,
                       configuration=configuration(engine), provenance=provenance(),
                       archive_provenance=archive.header.get('provenance'),
                       audit_retains_full_session=verify, frames_saved=False,
                       timing='Original sampled timestamps; unpaced replay without camera access')
        with event_log(output, session) as emit:
            for sample in archive:
                new = engine.push(sample)
                count += 1
                for reading in new:
                    emit(reading.to_dict())
                if verify:
                    groups.setdefault(engine.session, []).append(sample)
                    readings.extend(new)
            if not count:
                raise ValueError('Sample archive contains no measurements')
            audit = verify_batch(groups, readings, engine) if verify else None
            summary = dict(type='summary', mode='sample_replay', samples=count,
                source_sha256=digest.hexdigest(), finalized_windows=engine.finalized_windows,
                estimated_windows=engine.estimated_windows-engine.uncertain_windows,
                raw_estimated_windows=engine.estimated_windows, uncertain_windows=engine.uncertain_windows,
                resets=engine.resets, batch_parity=audit,
                final_state=engine.state(), frames_saved=False)
            emit(summary)
    (output/'stream-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary


def preview_frame(bgr, points, state, now, background=None):
    """A simple live view; no waveform is fabricated between completed readings."""
    from PIL import Image, ImageDraw
    from .demo_layout import text, clock
    from .regions import REGIONS

    face = bgr.copy()
    if background is not None:
        left,top,right,bottom=background['bounds']
        color=(146,117,86) if background['status']=='available' else (70,90,180)
        cv2.rectangle(face,(left,top),(right-1,bottom-1),color,2,cv2.LINE_AA)
    if points is not None:
        for indices in REGIONS.values():
            cv2.polylines(face, [np.rint(points[list(indices)]).astype(np.int32)], True, (58, 45, 217), 1, cv2.LINE_AA)
    image = Image.new('RGB', (1120, 700), '#FBFBFD')
    draw = ImageDraw.Draw(image)
    text(draw, 'PulseTrace', (40, 30), 28, bold=True)
    text(draw, f'Camera session · {clock(now)}', (1080, 38), 16, '#6E6E73', right=True)
    draw.line((40, 90, 1080, 90), fill='#E5E5EA')
    h, w = face.shape[:2]
    scale = min(640/w, 480/h)
    video = Image.fromarray(cv2.cvtColor(face, cv2.COLOR_BGR2RGB)).resize((round(w*scale), round(h*scale)))
    image.paste(video, (40+(640-video.width)//2, 120+(480-video.height)//2))
    text(draw, 'Heart rate', (730, 130), 21, '#6E6E73')
    value = '—' if state['bpm'] is None else f"{state['bpm']:.1f}"
    text(draw, value, (723, 185), 85)
    if state['bpm'] is not None:
        text(draw, 'BPM', (730, 285), 20, '#6E6E73')
    labels = dict(measuring='Gathering clean video', waiting_for_face='Position one face in view',
                  capture_stalled='Camera paused · reading cleared', estimate='Completed-window estimate',
                  unavailable='Estimate unavailable this window', uncertain='Uncertain · methods disagree')
    row = state['latest_window']
    unavailable_detail=None
    if state['status']=='unavailable' and row is not None:
        if row.get('unavailable_reason')=='quality_exclusion':
            labels['unavailable']='Tracking changes interrupted this window'
            quality=row.get('quality',{})
            longest=quality.get('longest_clean_pair',{}).get('duration_s')
            minimum=quality.get('minimum_continuous_seconds')
            if quality.get('window_policy')=='continuous' and longest is not None and minimum is not None:
                unavailable_detail=f'Clean stretch: {longest:.1f}s / {minimum:g}s needed'
        elif row.get('unavailable_reason')=='insufficient_pulse_support':
            labels['unavailable']='No consistent estimate this window'
            unavailable_detail='Face-region estimates did not agree'
    if state['status'] == 'estimate' and row is not None:
        agreement = row.get('quality',{}).get('method_agreement')
        if agreement is not None:
            labels['estimate'] = 'Methods agree · completed window' if agreement['status']=='agreement' else 'Single-method estimate'
    text(draw, labels[state['status']], (730, 350), 16, '#6E6E73')
    if state['status'] == 'uncertain':
        text(draw, 'Waiting for a consistent window', (730, 390), 16, '#6E6E73')
    if unavailable_detail is not None:
        text(draw,unavailable_detail,(730,390),16,'#6E6E73')
    if state['bpm'] is not None and row['analysis_start_s'] is not None:
        text(draw, f"{clock(round(row['analysis_start_s']))}–{clock(round(row['analysis_end_s']))} analyzed", (730, 390), 16, '#6E6E73')
    elif state['status'] == 'measuring' and state['next_available_at_s'] is not None:
        remaining = max(0, state['next_available_at_s']-now)
        text(draw, f'First window in {remaining:.1f}s', (730, 390), 16, '#6E6E73')
    text(draw, 'Keep still in steady, diffuse light', (40, 630), 17, '#6E6E73')
    if background is not None:
        label='Recording selected background' if background['status']=='available' else dict(
            face_not_tracked='Background paused · face not tracked',
            invalid_face_geometry='Background paused · face tracking unavailable',
            face_overlaps_background='Move your face away from the background box',
            insufficient_pixels='Background box is too small').get(background['reason'],'Background unavailable')
        text(draw,label,(40,606),14,'#567592' if background['status']=='available' else '#B45445')
    text(draw, '12-second windows · 6-second updates', (40, 668), 14, '#6E6E73')
    text(draw, 'Press Q or Esc to stop', (1080, 668), 14, '#6E6E73', right=True)
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def webcam(tracker, output, *, device=0, sampling='fractional', method='pos', consensus='patch',
           window_policy='continuous', seconds=None, preview=True, agreement_policy='flag', background_roi=None):
    from .capture import CameraSession

    if seconds is not None and (not np.isfinite(seconds) or seconds <= 0):
        raise ValueError('seconds must be positive and finite')
    engine = PulseStream(method=method, consensus=consensus, window_policy=window_policy,
                         agreement_policy=agreement_policy)
    sampler = FrameSampler(sampling=sampling,background_roi=background_roi)
    last_state = None
    processing = 0.
    interrupted = False
    metadata = dict(mode='webcam', synthetic=False, sampling=sampling,
            configuration=configuration(engine), frames_saved=False,
            rgb_samples_saved=True, samples_file='samples.jsonl',
            capture_pipeline='independent_latest_frame', capture_timing_version=1,
            timing='Independent acquisition; monotonic frame-read completion times, not camera exposure timestamps')
    if sampler.background_roi is not None:
        metadata['background_reference']=dict(roi=list(sampler.background_roi),coordinates='normalized XYWH',
            face_exclusion='whole ROI rejected on overlap with 10%-padded landmark bounds',
            use='recording only; no live lighting screen',skin_detection=False)
    background_counts={}
    with event_log(output, metadata) as emit, SampleWriter(Path(output)/'samples.jsonl', metadata) as archive:
        try:
            with CameraSession(tracker, sampler, device=device) as camera:
                try:
                    while seconds is None or time.monotonic()-camera.started < seconds:
                        try:
                            sample = camera.queue.get(timeout=.05)
                        except queue.Empty:
                            if camera.done.is_set():
                                if camera.error:
                                    raise OSError(camera.error)
                                break
                        else:
                            archive.write(sample)
                            if sample.background is not None:
                                label=sample.background['reason'] or 'available'
                                background_counts[label]=background_counts.get(label,0)+1
                            began = time.perf_counter()
                            readings = engine.push(sample)
                            elapsed = time.perf_counter()-began
                            processing += elapsed
                            for reading in readings:
                                emit(dict(**reading.to_dict(), emitted_at_s=time.monotonic()-camera.started,
                                          computation_seconds=elapsed, capture_timing=camera.statistics()))
                        now = time.monotonic()-camera.started
                        state = engine.state(now)
                        key = (state['status'], state['session'], state['bpm'])
                        if key != last_state:
                            emit(dict(type='state', source_time_s=now, **state))
                            print(json.dumps(dict(status=state['status'], bpm=state['bpm'])), flush=True)
                            last_state = key
                        if preview:
                            frame = camera.latest_preview(include_background=True)
                            if frame is not None:
                                bgr, points, _, background = frame
                                cv2.imshow('PulseTrace', preview_frame(bgr, points, state, now,background))
                            keypress = cv2.waitKey(1) & 0xFF
                            if keypress in (27, ord('q')):
                                break
                except KeyboardInterrupt:
                    interrupted = True
        except (OSError, ValueError, RuntimeError, cv2.error) as exc:
            emit(dict(type='error', status='unavailable', bpm=None, message=str(exc)))
            if isinstance(exc, cv2.error):
                raise OSError('Camera preview failed; try --no-preview: '+str(exc)) from exc
            raise
        finally:
            if preview:
                cv2.destroyAllWindows()
        summary = dict(type='summary', mode='webcam', sampled_frames=camera.frames,
            dropped_samples=camera.dropped_samples, finalized_windows=engine.finalized_windows,
            estimated_windows=engine.estimated_windows-engine.uncertain_windows,
            raw_estimated_windows=engine.estimated_windows, uncertain_windows=engine.uncertain_windows,
            resets=engine.resets, interrupted=interrupted,
            final_state=engine.state(time.monotonic()-camera.started), analysis_seconds=processing,
            saved_samples=archive.count, samples_file='samples.jsonl',
            capture_timing=camera.statistics(),
            frames_saved=False)
        if sampler.background_roi is not None:
            summary['background_reference']=dict(roi=list(sampler.background_roi),sample_status_counts=background_counts,
                                                  applied_to_estimates=False)
        emit(summary)
    (Path(output)/'stream-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary
