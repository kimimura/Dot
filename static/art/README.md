# Dot's art

Drop Lottie JSON files here and Dot switches from the vector placeholder to them automatically.
Nothing else to configure; the state machine, chat and triggers stay the same.

## Option A — one file per state (simplest)

Name the files after the states. Only `idle.json` is required; any missing state falls back to idle.

```
static/art/
  idle.json        default; loops
  reading.json     while a PDF is being read; loops
  thinking.json    while the model is working; loops
  asking.json      when Dot asks you a question; loops
  happy.json       on Yes / saved; plays once, then back to the previous state
  confused.json    on an error or "No"; loops
  sleepy.json      after 60 s idle; loops
  poked.json       when clicked; plays once
```

## Option B — one file with segments

If a single Lottie file holds all the poses on one timeline, add `manifest.json`:

```json
{
  "file": "dot.json",
  "segments": {
    "idle": [0, 60], "reading": [61, 120], "thinking": [121, 180],
    "asking": [181, 200], "happy": [201, 240], "confused": [241, 280],
    "sleepy": [281, 320], "poked": [321, 340]
  },
  "once": ["happy", "poked"]
}
```

Frame ranges are inclusive. A `manifest.json` can also map states to separate files:
`{"files": {"idle": "robot-idle.json", "happy": "robot-jump.json"}}`.

## Where to get files

- lottiefiles.com — search "robot character", "mascot", "cute character"; filter free.
  Download as **Lottie JSON** (not dotLottie, not GIF). Check the licence (CC-BY needs a credit).
- rive.app community — export to Lottie where available.
- A commissioned character from an animator: ask for Lottie export from After Effects (Bodymovin).

Keep files under ~500 KB each; the art box is 124×124 px in the chat column.
