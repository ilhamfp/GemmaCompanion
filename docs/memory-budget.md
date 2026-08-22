# Jetson memory budget

All values are measured on the Jetson. The 8 GB unified memory is shared by CPU and GPU.

| Checkpoint | Used RAM | Available RAM | Runtime/model disk | Result |
|---|---:|---:|---:|---|
| M0 idle recon | 923 MiB | 6.4 GiB | n/a | safe |
| M3 after audio verification | 934 MiB | 6.4 GiB | Whisper tiny.en 75 MiB; whisper.cpp 11 MiB; eSpeak CLI 68 KiB | safe |

The M3 speech processes are short-lived. The final row reports memory immediately after the accepted test; no model server remained resident.
