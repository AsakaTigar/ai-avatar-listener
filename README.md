# AI Avatar Listener · yachiyo

A listening console for the **B站 AI 主播 (ai-live-avatar)** voice pipelines. Two tabs, all
audio replayed from existing experiment artifacts — no parameter is changed here:

**🎤 唱歌 — RVC singing voice conversion (any singer → yachiyo timbre)**

* **Parameter matrix A–F** — the same 123.5 s vocal segment through six RVC parameter sets
  (`f0` extractor rmvpe/pm × `index_rate` 0/0.3/0.5 × `protect` 0.33/0.5). Pick any two in the
  A/B player, snap-play both, and the objective metrics table (F0 correlation, median / P90
  error in cents, fraction within 50 cents) is shown alongside.
* **Finished tracks** — 第一首完整歌, the *perfect* mix, song3 (告白气球) with its source
  reference, plus the 40 s cover segment (original vs. converted) for a length-matched A/B.

**🗣️ 说话 — Qwen3-TTS cloned-voice line**

* Reference voices → zero-shot clone (non-streaming / streaming) → v1–v4 fine-tunes →
  tone/persona candidates → multilingual (zh / ja / en).

## Layout

```
app.py                    Streamlit shell; players are self-contained HTML components
data/audio/*.mp3          curated artifacts (22.05 kHz mono 96 kbps; matrix + finals from lossless sources)
data/manifest.json        item list: id, file, description, duration
data/peaks.json           waveform envelopes for the A/B lanes (computed from the lossless sources)
data/rvc_matrix_results.json   the RVC matrix objective metrics
```

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Provenance

Assembled from the `ai-live-avatar` experiment artifacts (`data/mp3`, `data/listen`,
`data/test_output`, `data/mp3/rvc_matrix_wav`). The RVC matrix numbers come from
`data/mp3/rvc_matrix_results.json`; peaks were computed from the lossless sources at build
time. Internal listening only — no listening-result claim.

## Listening safety (ear protection)

* **Master volume** slider per player with a hard ceiling: the top of the slider is `-1.4 dBFS`.
* **Soft limiter** on the master bus (threshold `-3 dBFS`, ratio 20) — the singing takes and the
  TTS rows cannot spike.
* **Fade in / fade out** on every play, pause and reset (no clicks); switching rows stops the
  previous take with a fade.
* LAN use: the app binds `0.0.0.0`; open `http://<mac-lan-ip>:8532` from a phone on the same Wi-Fi.
