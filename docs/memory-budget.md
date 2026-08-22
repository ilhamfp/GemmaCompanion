# Jetson memory budget

All values are measured on the Jetson. The 8 GB unified memory is shared by CPU and GPU.

| Checkpoint | Used RAM | Available RAM | Runtime/model disk | Result |
|---|---:|---:|---:|---|
| M0 idle recon | 923 MiB | 6.4 GiB | n/a | safe |
| M3 after audio verification | 934 MiB | 6.4 GiB | Whisper tiny.en 75 MiB; whisper.cpp 11 MiB; eSpeak CLI 68 KiB | safe |
| M4 Gemma loaded after multimodal inference | 4.0 GiB | 3.3 GiB | Gemma 4 E2B Q4_0 3.10 GiB; projector 986 MiB; mmap-backed llama.cpp CUDA runtime | safe |
| M5 after agent-loop verification | 4.1 GiB | 3.2 GiB | Gemma and projector resident; two 1024px vision calls; JSONL logging | safe |
| M6 after two consecutive Akinator games | 4.3 GiB | 3.0 GiB | Gemma and projector resident; fixed room scans, autonomous re-checks, eSpeak playback | safe |

The M3 speech processes are short-lived. Its row reports memory immediately after the accepted test; no model server was resident at that checkpoint.

The M4 row is the accepted `free -h` reading while `llama-server` remained resident after text, live-camera vision, and tool-call inference. The verifier aborts below 500 MiB available.
