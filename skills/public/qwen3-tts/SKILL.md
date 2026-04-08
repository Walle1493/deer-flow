---
name: qwen3-tts
description: Use this skill when the user requests text-to-speech (TTS) audio generation. It calls a self-hosted HTTP TTS inference service and saves the resulting audio file for download/sharing (e.g. in Feishu).
allowed-tools: Bash(python *)
---

# Qwen3-TTS (Self-hosted) Skill

## Overview

This skill converts input text into speech by calling your self-hosted TTS inference service (HTTP API). The service returns a short-lived `audio_url`; this skill downloads it and saves a WAV file to `/mnt/user-data/outputs/`.

## Required Setup

Configure the TTS service base URL via environment variable (recommended to set it in your `.env` / deployment environment, not in code):

- `QWEN3_TTS_BASE_URL`: e.g. `http://<your-tts-host>:10145`

### WSL networking note (common)

If DeerFlow runs inside WSL and cannot route to intranet `10.x` directly, expose the TTS service via a Windows localhost forwarder and point the skill to that address, e.g.:

- `QWEN3_TTS_BASE_URL=http://127.0.0.1:55145`

This skill will also automatically download `audio_url` through the forwarder when needed (so WSL does not have to reach `10.x`).

## Workflow

### Step 1: Decide output file path

Pick a deterministic output path under:

- `/mnt/user-data/outputs/`

Example:

- `/mnt/user-data/outputs/tts.wav`

### Step 2: Run the generation script

Call:

```bash
python /mnt/skills/public/qwen3-tts/scripts/generate.py \
  --text "你好，这是一个只传 text 的测试。" \
  --output-file /mnt/user-data/outputs/tts.wav
```

Optional flags:

- `--base-url`: override `QWEN3_TTS_BASE_URL`
- `--timeout-sec`: request timeout (default 120)
- `--meta-json`: save response metadata JSON alongside the audio

Example (with metadata):

```bash
python /mnt/skills/public/qwen3-tts/scripts/generate.py \
  --text "请用更有感情的语气读这句话。" \
  --output-file /mnt/user-data/outputs/tts-emotional.wav \
  --meta-json /mnt/user-data/outputs/tts-emotional.json
```

## Output Handling

- The script writes a WAV file to `--output-file`
- Share the generated audio with the user (and later Feishu) from `/mnt/user-data/outputs/`

[!NOTE]
Do NOT read the python file, instead just call it with the parameters.

