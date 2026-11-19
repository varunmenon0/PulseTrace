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
                note='Same tracked samples; parity is not physiological validation or a throughput benchmark')


def replay(video, tracker, output, *, sampling='fractional', method='pos', consensus='patch',
           window_policy='continuous', verify=False, synthetic=False):
    from .video import VideoReader

    sampler = FrameSampler(sampling=sampling)
    engine = PulseStream(method=method, consensus=consensus, window_policy=window_policy)
    groups, readings = {}, []  # Populated only by the explicitly requested full-session audit.
    frames = 0
    last_state = None
    started = time.perf_counter()
    with event_log(output, dict(mode='recorded_streaming_replay', synthetic=synthetic,
            sampling=sampling, audit_retains_full_session=verify, configuration=configuration(engine),
            timing='Decoded source timestamps; unpaced replay; EOF does not finalize incomplete look-ahead')) as emit:
        with VideoReader(video) as reader:
            for frame in reader:
                points = tracker.detect(frame.bgr, frame.time)
                if synthetic and hasattr(tracker, 'background_rgb'):
                    tracker.background_rgb.clear()  # Fixture diagnostics are not needed by the streaming engine.
                sample = sampler.sample(frame.bgr, points, frame.time)
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
            estimated_windows=engine.estimated_windows, resets=engine.resets, batch_parity=audit,
            final_state=engine.state(), processing_seconds=time.perf_counter()-started,
            incomplete_tail_policy='No EOF flush or fabricated future samples')
        emit(summary)
    (Path(output)/'stream-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary


def preview_frame(bgr, points, state, now):
    """A simple live view; no waveform is fabricated between completed readings."""
    from PIL import Image, ImageDraw
    from .demo_layout import text, clock
    from .regions import REGIONS

    face = bgr.copy()
    if points is not None:
        for indices in REGIONS.values():
            cv2.polylines(face, [np.rint(points[list(indices)]).astype(np.int32)], True, (58, 45, 217), 1, cv2.LINE_AA)
    image = Image.new('RGB', (1120, 700), '#FBFBFD')
    draw = ImageDraw.Draw(image)
    text(draw, 'PulseTrace', (40, 30), 28, bold=True)
    text(draw, 'Camera session', (1080, 38), 16, '#6E6E73', right=True)
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
                  unavailable='Estimate unavailable this window')
    text(draw, labels[state['status']], (730, 350), 16, '#6E6E73')
    row = state['latest_window']
    if state['bpm'] is not None and row['analysis_start_s'] is not None:
        text(draw, f"{clock(round(row['analysis_start_s']))}–{clock(round(row['analysis_end_s']))} analyzed", (730, 390), 16, '#6E6E73')
    elif state['status'] == 'measuring' and state['next_available_at_s'] is not None:
        remaining = max(0, state['next_available_at_s']-now)
        text(draw, f'First window in {remaining:.1f}s', (730, 390), 16, '#6E6E73')
    text(draw, 'Keep still in steady, diffuse light', (40, 630), 17, '#6E6E73')
    text(draw, '12-second windows · 6-second updates', (40, 668), 14, '#6E6E73')
    text(draw, 'Press Q or Esc to stop', (1080, 668), 14, '#6E6E73', right=True)
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def webcam(tracker, output, *, device=0, sampling='fractional', method='pos', consensus='patch',
           window_policy='continuous', seconds=None, preview=True):
    from .capture import CameraSession

    if seconds is not None and (not np.isfinite(seconds) or seconds <= 0):
        raise ValueError('seconds must be positive and finite')
    engine = PulseStream(method=method, consensus=consensus, window_policy=window_policy)
    sampler = FrameSampler(sampling=sampling)
    last_state = None
    processing = 0.
    interrupted = False
    with event_log(output, dict(mode='webcam', synthetic=False, sampling=sampling,
            configuration=configuration(engine), frames_saved=False,
            timing='Monotonic frame-read completion times; not camera exposure timestamps')) as emit:
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
                            began = time.perf_counter()
                            readings = engine.push(sample)
                            elapsed = time.perf_counter()-began
                            processing += elapsed
                            for reading in readings:
                                emit(dict(**reading.to_dict(), emitted_at_s=time.monotonic()-camera.started,
                                          computation_seconds=elapsed))
                        now = time.monotonic()-camera.started
                        state = engine.state(now)
                        key = (state['status'], state['session'], state['bpm'])
                        if key != last_state:
                            emit(dict(type='state', source_time_s=now, **state))
                            print(json.dumps(dict(status=state['status'], bpm=state['bpm'])), flush=True)
                            last_state = key
                        if preview:
                            frame = camera.latest_preview()
                            if frame is not None:
                                bgr, points, _ = frame
                                cv2.imshow('PulseTrace', preview_frame(bgr, points, state, now))
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
            estimated_windows=engine.estimated_windows, resets=engine.resets, interrupted=interrupted,
            final_state=engine.state(time.monotonic()-camera.started), analysis_seconds=processing,
            frames_saved=False)
        emit(summary)
    (Path(output)/'stream-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary
