"""Rendered, lossless video fixtures with skin-localized, known pulse modulation."""
import cv2
import numpy as np

from .synthetic import SyntheticTracker


PROFILES = {
    'clean': dict(noise_std=0., lighting_hz=0., lighting_fraction=0.),
    'mild_noise': dict(noise_std=.25, lighting_hz=0., lighting_fraction=0.),
    'slow_light': dict(noise_std=0., lighting_hz=.15, lighting_fraction=.04),
    'periodic_light': dict(noise_std=0., lighting_hz=1.8, lighting_fraction=.05),
}
SIZE = (320, 240)
PULSE_RGB = (.6, 3., .2)


class ControlledTracker(SyntheticTracker):
    """Known fixture geometry; also observe an unmodulated corner reference."""

    def __init__(self):
        self.background_rgb = []

    def detect(self, bgr, time):
        h, w = bgr.shape[:2]
        points = super().detect(bgr, time)
        points[33], points[263] = (.3*w, .35*h), (.7*w, .35*h)
        self.background_rgb.append(bgr[:max(1, h//10), :max(1, w//10)].mean(axis=(0, 1))[::-1])
        return points


def scene():
    """Simple face geometry keeps all sampled skin patches clear of features."""
    w, h = SIZE
    image = np.full((h, w, 3), [60, 45, 35], dtype=np.uint8)
    cv2.ellipse(image, (w//2, h//2), (round(.38*w), round(.47*h)), 0, 0, 360, (80, 110, 160), -1)
    for x in (.36, .64):
        cv2.ellipse(image, (round(x*w), round(.35*h)), (round(.055*w), round(.025*h)),
                    0, 0, 360, (225, 225, 225), -1)
        cv2.circle(image, (round(x*w), round(.35*h)), 4, (35, 35, 35), -1)
    cv2.line(image, (round(.5*w), round(.42*h)), (round(.47*w), round(.59*h)), (65, 95, 140), 2)
    cv2.ellipse(image, (w//2, round(.72*h)), (round(.12*w), round(.05*h)), 0, 0, 180, (60, 75, 115), 2)
    cv2.putText(image, 'PulseTrace synthetic fixture', (8, h-6), cv2.FONT_HERSHEY_SIMPLEX, .35, (200, 200, 200), 1)
    skin = np.all(image == [80, 110, 160], axis=2)
    return image.astype(float), skin


def make_controlled_video(path, *, bpm=72., seconds=20., fps=30., seed=7, profile='clean'):
    if not np.isfinite([bpm, seconds, fps]).all() or not 40 < bpm < 200 or seconds < 10 or not 10 <= fps <= 240:
        raise ValueError('Fixture requires 40<BPM<200, >=10 seconds and 10–240 FPS')
    if profile not in PROFILES:
        raise ValueError('Unknown controlled profile')
    base, skin = scene()
    config = PROFILES[profile]
    rng = np.random.default_rng(seed)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'FFV1'), fps, SIZE)
    if not writer.isOpened():
        raise ValueError('Lossless FFV1 encoder unavailable')
    frames = round(seconds*fps)
    try:
        for i in range(frames):
            t = i/fps
            image = base.copy()
            image[skin] += np.sin(2*np.pi*bpm/60*t)*np.array(PULSE_RGB)[::-1]
            if config['noise_std']:
                image[skin] += rng.normal(0, config['noise_std'], (int(skin.sum()), 3))
            image *= 1 + config['lighting_fraction']*np.sin(2*np.pi*config['lighting_hz']*t)
            writer.write(np.clip(np.rint(image), 0, 255).astype(np.uint8))
    finally:
        writer.release()
    return dict(synthetic=True, profile=profile, expected_bpm=bpm, fps=fps,
                seconds=seconds, encoded_frames=frames, width=SIZE[0], height=SIZE[1],
                codec='FFV1', seed=seed, pulse_rgb_amplitude=list(PULSE_RGB),
                settings=dict(config), tracking='Known rendered geometry, not MediaPipe inference')


def evaluate_controlled(extraction, background_rgb, *, consensus_policy='patch'):
    """Analyze decoded samples without consulting expected BPM or fixture settings."""
    from .agreement import method_agreement
    from .patches import PATCHES, consensus
    from .regions import REGIONS
    from .signal import analyze
    from .zone_consensus import hierarchical_consensus
    if consensus_policy not in ('patch', 'zone'):
        raise ValueError('Unknown consensus policy')
    choose = hierarchical_consensus if consensus_policy == 'zone' else consensus

    def estimate(rgb, method):
        try:
            result = analyze(extraction.time, rgb, method=method)
            return dict(bpm_candidate=result.bpm, peak_fraction=result.peak_fraction)
        except ValueError as error:
            return dict(bpm_candidate=None, error=str(error))

    background = estimate(np.asarray(background_rgb), 'green')
    methods = {}
    for method in ('green', 'pos'):
        regions = {n: estimate(rgb, method) for n, rgb in extraction.rgb.items()}
        patches = {n: estimate(rgb, method) for n, rgb in extraction.patch_rgb.items()}
        methods[method] = dict(regions=regions, patches=patches,
            region_consensus=consensus({n: r['bpm_candidate'] for n, r in regions.items()}, {n:n for n in REGIONS}),
            patch_consensus=choose({n: r['bpm_candidate'] for n, r in patches.items()}, PATCHES))
    layout = 'patch_consensus' if extraction.patch_rgb else 'region_consensus'
    return dict(background=background, consensus_policy=consensus_policy, methods=methods,
                agreement_layout=layout,
                method_agreement=method_agreement(methods['green'][layout]['bpm_candidate'],
                    methods['pos'][layout]['bpm_candidate'], background_bpm=background['bpm_candidate']))
