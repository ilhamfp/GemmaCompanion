## M0 Recon
status: DONE
verified_by: scripts/recon.sh
verified_at: 2026-08-22 11:00 SGT
evidence: |
  OBSBOT video nodes: /dev/video0,/dev/video1 (capture: /dev/video0)
  AT-CSP1 ALSA capture card: 3; playback card: 3
  CUDA: driver API 13.2 (nvidia-l4t-cuda installed); Python: Python 3.12.3
  Available RAM: 6.4Gi
  Available disk on /: 425G
fallback_taken: none
commit: bcaa8cd
notes: v4l2-ctl is absent, so recon used read-only sysfs/direct V4L2 ioctls. Pan and tilt absolute controls are exposed on /dev/video0. Jetson wall clock is unset (1970); verified_at uses the Mac SGT clock.

## M1 Camera capture
status: DONE
verified_by: scripts/test_camera.py
verified_at: 2026-08-22 11:03 SGT
evidence: |
  device: /dev/video0
  capture_path: /home/iputra/gemma-companion/captures/capture-a08718edb6eb4ddf9f6379098d99da87.jpg
  dimensions: 1024x576; bytes: 62710; contrast_stddev: 83.61
  elapsed_seconds: 0.392
  result: PASS fresh JPEG captured in under 2 seconds
fallback_taken: none
commit: 08b87f8
notes: Uses OBSBOT hardware MJPEG through GStreamer and discards four warm-up frames. The first cold-open run took 2.028 s and failed; the immediate acceptance rerun passed. Frame copied to Mac as artifacts/m1-camera.jpg (SHA-256 bc6a3c9ceaf292c113394a1c72e49a993bf3bc021a2fb545627343d7243ec8e0) and visually confirmed as the workspace view.

## M2 PTZ control
status: DONE
verified_by: scripts/test_ptz.py
verified_at: 2026-08-22 11:05 SGT
evidence: |
  method: uvc
  sequence: look_left,capture,look_right,capture,look_center
  frames: left=/home/iputra/gemma-companion/captures/ptz/capture-21bd82831ee442f6a6d9de25e4b6ef1f.jpg; right=/home/iputra/gemma-companion/captures/ptz/capture-1126905570eb412e956893d519583ea5.jpg
  mean_pixel_diff: 76.458; threshold: 8.000
  result: PASS physical PTZ frames differ and camera returned center
fallback_taken: none
commit: 3ca6e19
notes: Standard UVC pan_absolute/tilt_absolute controls are driven with direct V4L2 ioctls because v4l2-ctl is absent. Movement is clamped to pan +/-60 degrees and tilt +/-30 degrees, safely inside hardware limits. Left/right frames were copied to the Mac and visibly differ.

## M3 Audio I/O
status: FALLBACK
verified_by: scripts/test_audio.py
verified_at: 2026-08-22 11:14 SGT
evidence: |
  recording: /home/iputra/gemma-companion/captures/audio/recording-88e82b44bd514e27b496409f8f5e8c2a.wav; duration_seconds: 3.000
  transcript: Gemma, please find my glasses now.
  spoken: Hello, I am Gemma; device: plughw:3,0
  text_fallback: yes; status: PASS
  result: PASS 3s record, offline STT, TTS playback, and text mode
fallback_taken: eSpeak NG TTS because Piper was not installed; its own verification passed and the human reported hearing playback.
commit: f148b46
notes: AT-CSP1 is ALSA plughw:3,0. STT is whisper.cpp 1.9.3 with the 75 MiB tiny.en model, fully offline. A separate --text run exited 0. The AT-CSP1 echo-cancels its own playback, so the verifier gives an audible cue and transcribes the human response rather than using self-loopback.

## M4 Gemma on the Jetson
status: DONE
verified_by: scripts/test_gemma.py
verified_at: 2026-08-22 11:38 SGT
evidence: |
  model: Gemma 4 E2B; tag: gemma4:e2b-it-qat; quantization: Q4_0; runtime: llama.cpp b1-9d77fa172 CUDA jetpack6
  text_to_text: PASS; latency_seconds: 0.306; response: GEMMA_READY
  image_to_text: PASS; latency_seconds: 2.099; response: The image displays a laptop, a person, and a chair.
  tool_call: PASS; latency_seconds: 0.550; parsed: look_right
  free_h_after_load: Mem:           7.3Gi       4.0Gi       135Mi       5.2Mi       3.4Gi       3.3Gi; result: PASS Gemma text, vision, tool call, latency, and RAM headroom
fallback_taken: none
commit: b81c6cf
notes: Official Gemma 4 E2B instruction-tuned QAT Q4_0 weights and multimodal projector run through llama.cpp's JetPack 6 CUDA backend. The generic CUDA backend was rejected after showing 0% GPU activity and 42.98 s text latency. The accepted 1024px live-camera vision request stayed well below 20 s; available RAM stayed safely above the 500 MiB guard.

## M5 Agent loop
status: DONE
verified_by: scripts/test_loop.py
verified_at: 2026-08-22 11:41 SGT
evidence: |
  gemma_action: look_left; issued_by: Gemma; tool_calls: 1/8
  physical_result: pan=-45.0; tilt=0.0; mean_pixel_diff=75.723
  post_look_message: NEW_OBJECT: a microphone on the desk
  session_log: /home/iputra/gemma-companion/logs/session-19700101-084916-060515.jsonl; events: 10; order: decide,look,capture,reference
  result: PASS Gemma issued LOOK and its next visual message used only the new physical frame
fallback_taken: none
commit: 8ba3e77
notes: The shared bounded loop checks the 500 MiB RAM guard around every inference, permits at most 8 tool calls and 12 questions, stores compact directional visual memory, and recenters in a finally block. The Jetson wall clock remains unset, so the log filename is 1970 while verified_at uses the Mac SGT clock. After-load RAM was 4.1 GiB used and 3.2 GiB available; disk had 418 GiB free.

## M6 Akinator demo
status: DONE
verified_by: make demo-akinator
verified_at: 2026-08-22 12:03 SGT
evidence: |
  game_1: PASS; questions=2; gemma_move=look_left; duration_seconds=27.903; guess=I guess your object is the laptop.
  game_2: PASS; questions=1; gemma_move=look_left; duration_seconds=21.759; guess=I guess your object is the laptop.
  consecutive_games: 2/2 PASS; text_fallback: yes; physical_moves: 2
  session_logs: /home/iputra/gemma-companion/logs/session-19700101-090946-763935.jsonl; /home/iputra/gemma-companion/logs/session-19700101-091014-667650.jsonl
  result: PASS two consecutive full Akinator games with Gemma-initiated physical camera moves
fallback_taken: none
commit: 1046829
notes: The requested replay passed with keyboard/scripted truthful answers and live AT-CSP1 TTS. Both latest logs independently contain GEMMA_LOOK_DECISION followed by physical LOOK and GAME_RESULT PASS, with no capture retry. The human confirmed in chat that both speech and physical OBSBOT movement were observed. After the replay, 2.9 GiB RAM and 418 GiB disk remained available.

## M7 Elderly requested-object finder
status: DONE
verified_by: make demo-elderly
verified_at: 2026-08-22 12:28 SGT
evidence: |
  found_run_1: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=On the white tabletop; duration_seconds=25.456
  found_run_2: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=on the white table; duration_seconds=24.835
  found_run_3: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=On the white tabletop; duration_seconds=25.627
  negative_run: PASS; target=red umbrella; searched=center,left,right,up,down; response=I couldn't find the red umbrella from here; please check its usual place.; log=/home/iputra/gemma-companion/logs/session-19700101-093544-012493.jsonl
  result: PASS requested object found 3/3 out of initial view and honest not-found 1/1
fallback_taken: Audio-Technica tabletop speaker substituted for glasses at the human's explicit request after physical glasses could not be staged inside the useful camera sweep; a genuinely absent red umbrella supplied the honest not-found test.
commit: 6b55f17
notes: The generalized elderly finder retains the same confirmation, systematic search, plain location, uncertainty, and medical-safety behavior. Every positive log contains a Gemma-issued look_left before a grounded speaker detection in the new frame; no accepted run contains CAPTURE_RETRY. The human confirmed in chat that the spoken result and physical OBSBOT movement worked. After the run, 2.8 GiB RAM and 418 GiB disk remained available.

## M8 Ship and demo handoff
status: IN_PROGRESS
verified_by: make reset + unauthenticated public repository audit
verified_at: 2026-08-22 12:51 SGT
evidence: |
  camera_center: (0.0, 0.0)
  session_state: fresh (each demo starts a new bounded session; logs retained)
  tracked_weights: none
  public_repository: PASS https://github.com/ilhamfp/GemmaCompanion (HTTP 200, unauthenticated)
  result: PASS README, LICENSE, reset, clean assets, and public push
fallback_taken: none
commit: 4da493b
notes: Code shipping is complete and public. M8 remains IN_PROGRESS only for the human-owned demo video and Devpost submission; the dry-run and recording checklist is docs/demo-checklist.md.
