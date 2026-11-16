# PulseTrace demonstration

`PulseTrace-Demo.mp4` is a complete annotated replay of a public UBFC-rPPG
recording, rendered at 1440×900 and 15 presentation FPS. `demo-preview.png` is a
frame from the same render. These are curated documentation assets included at
the repository owner's request; raw recordings and detailed measurement tables
are excluded from Git.

Source: UBFC-rPPG subject 16, acquired from the
[public mirror](https://huggingface.co/datasets/thachha901/UBFC).
See the [official dataset](https://sites.google.com/view/ybenezeth/ubfcrppg),
[checksum manifest](../examples/real-video-recovery/subject16/source.json), and
[selection and evaluation protocol](../PUBLIC_DEMONSTRATION.md).
The project's MIT license does not replace upstream dataset terms.

The video shows recorded, completed-window analysis. The red line is the
estimated pulse; the dashed gray line uses original sensor labels over matching
analyzed support with an assumed zero elapsed-time offset. The sensor labels do
not enter the estimator. All windows, including less accurate estimates, are
shown. The selected demonstration is separate from the frozen five-recording
evaluation and does not establish clinical accuracy or live-camera latency.
