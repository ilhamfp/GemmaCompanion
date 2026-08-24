# Jetson memory budget

All values are measured on the Jetson. The 8 GB unified memory is shared by CPU and GPU.

| Checkpoint | Used RAM | Available RAM | Runtime/model disk | Result |
|---|---:|---:|---:|---|
| M0 idle recon | 923 MiB | 6.4 GiB | n/a | safe |
| M3 after audio verification | 934 MiB | 6.4 GiB | Whisper tiny.en 75 MiB; whisper.cpp 11 MiB; eSpeak CLI 68 KiB | safe |
| M4 Gemma loaded after multimodal inference | 4.0 GiB | 3.3 GiB | Gemma 4 E2B Q4_0 3.10 GiB; projector 942 MiB; mmap-backed llama.cpp CUDA runtime | safe |
| M5 after agent-loop verification | 4.1 GiB | 3.2 GiB | Gemma and projector resident; two 1024px vision calls; JSONL logging | safe |
| M6 after two consecutive Akinator games | 4.3 GiB | 3.0 GiB | Gemma and projector resident; fixed room scans, autonomous re-checks, eSpeak playback | safe |
| M7 after three found runs and one absent run | 4.5 GiB | 2.8 GiB | Gemma and projector resident; grounded two-step vision/tool decisions; eSpeak playback | safe |
| M9 Gemma plus resident Kokoro acceptance | +419.5 MiB TTS process RSS | 3.068 GiB | Kokoro-82M ONNX 310 MiB; voices 27 MiB; CPUExecutionProvider | safe |

The M3 speech processes are short-lived. Its row reports memory immediately after the accepted test; no model server was resident at that checkpoint.

The M4 row is the accepted `free -h` reading while `llama-server` remained resident after text, live-camera vision, and tool-call inference. The verifier aborts below 500 MiB available.

The M9 row was measured by `scripts/test_tts.py` with the Gemma server running. It stays below the 800 MiB TTS resident cap and above the 2.0 GiB available-memory floor required by `docs/VOICE.md`.
