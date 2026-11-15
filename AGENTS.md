# PulseTrace working repository

This directory is the canonical working copy. The 12-patch experiment is enabled
with --patches; the original three parent regions remain available for comparison.
Use Git commits for changes, rather than editing or exchanging source ZIP files.

## Validation

Install using python -m pip install -e '.[dev]' and run python -m pytest -q.
Keep the model-backed MediaPipe integration test optional unless public assets
are explicitly available. Do not commit recordings, downloaded models, outputs,
credentials, or local environment files.

## Scientific constraints

Keep baseline comparisons on the same frames, filters and motion exclusions.
Spectral agreement is not validation of a human pulse. Do not tune to a subject's
expected BPM. Report synthetic fixtures separately from natural video results.
No evaluated deepfake classifier or throughput benchmark is established here.

## Version control

Preserve existing history and remote commits. Work on a feature branch, inspect
diffs, run relevant tests, then commit. Never force-push or delete a repository
as part of routine synchronization.
