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
notes: AT-CSP1 is ALSA plughw:3,0. STT is whisper.cpp 1.9.3 with the 75 MiB tiny.en model, fully offline. A separate --text run exited 0. The AT-CSP1 echo-cancels its own playback, so the verifier gives an audible cue and transcribes the human response rather than using self-loopback. Voice was upgraded in M9; see the M9 Voice upgrade block.

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
notes: Code shipping is complete and public. The no-Mac boot unit passes `systemd-analyze verify`, but it is not installed (`is-enabled: not-found`, `is-active: inactive`) because GOAL.md requires the human to authorize the one-time sudo command. M8 remains IN_PROGRESS for that installation, the physical power-cycle rehearsal, and the human-owned demo video and Devpost submission; the dry-run and recording checklists are docs/demo-checklist.md and docs/DEMO_FLOW.md.

## M9 Voice upgrade
status: DONE
verified_by: scripts/test_tts.py, scripts/test_audio.py, make demo-akinator
verified_at: 2026-08-22 13:45 SGT
evidence: |
  engine: kokoro-onnx 0.6.1; voice: af_heart; sample_rate: 24000; provider: CPUExecutionProvider
  load_seconds: 2.482
  first_audio_seconds: 1.320; limit: <1.5
  total_seconds: 2.905; limit: <3.0
  cached_play_seconds: 0.001; limit: <0.2
  free_available_gib: 3.068; limit: >2.0; tts_resident_mib: 419.5; limit: <=800
  test_wav: /home/iputra/gemma-companion/artifacts/tts-sample.wav
  result: PASS natural resident CPU TTS meets warm, cached, and memory limits
engine: kokoro-onnx af_heart 1.0
fallback_taken: none
commit: e6e96f2
notes: The human audition choice was verbatim: `af_heart, 1.0 is good, let's do it`. With Gemma running, 3.068 GiB was available after load and the resident TTS process used 419.5 MiB. The current keyboard text fallback exited 0 and unchanged offline STT re-transcribed the accepted live AT-CSP1 recording as `Gemma, please find my glasses now.` The human confirmed the new playback was audible: `let's just assume it's working, i hear it the first time`. The accepted Akinator game reported `look_announcement_overlap: PASS` for `Let me look over there.` during Gemma's `look_left` move.

## M11 Five-beat live companion flow
status: DONE
verified_by: scripts/test_demo_flow.py + scripts/test_scam_vision.py
verified_at: 2026-08-22 14:53 SGT
evidence: |
  fixture_text: URGENT; bank locked; shortened link; one-time passcode request
  gemma_response: This message has several warning signs, such as the urgent tone and the request to reply with a one-time passcode. You should not click the link or share any codes. Please verify the sender through an independent, trusted channel.
  latency_seconds: 1.991; limit: <5.000
  advice: PASS; grounded warning signs and cautious next step
  result: PASS Gemma read and assessed a visible scam SMS
fallback_taken: none
commit: 719d589
notes: The same Jetson verification session also produced the exact `Hi, I'm Gemma!` cue after a fresh frame, physically moved left and right, described distinct fresh views, had Gemma issue `find_object` with target `AirPods`, and routed the scam question to a fresh camera observation. The finder reuses the M7 physically verified systematic search and now supports latest-turn cancellation. Final AirPods placement, a real phone screen, no-Mac boot, and the demo video remain human-owned M8 rehearsal work.

## M12 Live AirPods finder recovery
status: DONE
verified_by: scripts/test_live_finder.py
verified_at: 2026-08-22 15:45 SGT
evidence: |
  airpods_positive: PASS; direction=center; location=on the dark tabletop in the center; duration_seconds=5.797
  absent_negative: PASS; target=bright magenta stapler; duration_seconds=25.229
  coverage_moves: look_left,look_right,look_up,look_down
  logs: positive=/home/iputra/gemma-companion/logs/session-19700101-090221-650921.jsonl; negative=/home/iputra/gemma-companion/logs/session-19700101-090227-520270.jsonl
  result: PASS live AirPods detection and complete honest physical sweep
fallback_taken: none
commit: 1c8267e
notes: The original live miss was traced to Whisper converting `Find my AirPods` into `Fine. My iPhone`; the same captured frame immediately identified the case when given the correct target. The offline speech prompt now preserves AirPods, Gemma expands it to `small white Apple AirPods wireless-earbud charging case`, and the finder starts on the front tabletop. Two additional final-code live repetitions passed, for 3/3 total, at 5.771 and 5.489 seconds. A bounded decision retry handles invalid narrated directions, textual llama.cpp tool serialization is parsed safely, markdown locations are reduced to plain speech, and a deliberately absent target proved the complete physical sweep without hallucination. The exact `CompanionSession.handle_text("Find my AirPods.")` handoff then passed in 8.237 seconds with `find_found` and `on the black tabletop`.

## M13 Obscure-placement AirPods hardening
status: DONE
verified_by: scripts/test_live_finder.py
verified_at: 2026-08-22 16:19 SGT
evidence: |
  airpods_positive: PASS; direction=right; location=near a table; duration_seconds=20.353
  absent_negative: PASS; target=bright magenta stapler; duration_seconds=33.829
  coverage_moves: look_left,look_right,look_up,look_down
  logs: positive=/home/iputra/gemma-companion/logs/session-19700101-073712-954047.jsonl; negative=/home/iputra/gemma-companion/logs/session-19700101-073733-377924.jsonl
  result: PASS live AirPods detection and complete honest physical sweep
fallback_taken: none
commit: 50c433d
notes: A blind miss was traced to a partially clipped AirPods case at the extreme edge of a physically covered frame. Wide misses now receive one four-panel magnified edge inspection; target rewriting cannot discard product identity; a target-blind second observation rejects explicit color conflicts; detail JPEGs are atomic and size-validated; and a model request is bounded to 30 seconds. The exact hard frame passed 3/3, a newly hidden live placement passed 3/3 at direction=right in 23.651, 20.266, and 21.786 seconds, and the full CompanionSession handoff found it at direction=right in 24.508 seconds. Per the human's explicit instruction, this commit was synced to the Jetson but was not pushed to GitHub. The installed service still needs a human-authorized restart to load the new process image.

## M14 Arbitrary visible-reference routing
status: DONE
verified_by: scripts/test_visual_routing.py
verified_at: 2026-08-22 16:30 SGT
evidence: |
  visual_route_2: PASS; prompt=Can you identify this object?; action=visual_question; router=none; latency_seconds=2.614; frame=/home/iputra/gemma-companion/captures/companion/capture-66c3be089c2b4eb2a827351c7b20cf60.jpg
  visual_route_3: PASS; prompt=What is written on this label?; action=visual_question; router=inspect_view; latency_seconds=2.257; frame=/home/iputra/gemma-companion/captures/companion/capture-95ebd9f5d1c541139b2a95e85810cf27.jpg
  negative_controls: PASS; general knowledge stayed chat; misplaced object stayed find_object
  fresh_frames: PASS; unique=3/3
  result: PASS arbitrary visible-reference wording captured fresh camera frames
fallback_taken: none
commit: f1fd4a9
notes: The new inspect_view tool lets Gemma request a fresh camera frame for visible references, while a semantic deictic fallback guarantees current-object, holding, color, identity, label, and screen questions do not become camera-less chat when the small model omits the tool call. `What color is the object I'm holding?` also passed with action=visual_question in 2.557 seconds on its own unique frame. General knowledge remained chat, `Find my blue mug` and `Find my AirPods` remained find_object, and the full boot cue, physical PTZ, and fresh-vision regression passed. Companion camera capture now retries three transient malformed frames. Per the human's instruction, no GitHub push was performed; this change was synced only to the Jetson and requires a human-authorized service restart to load.

## M15 Phrase-free agentic companion
status: DONE
verified_by: scripts/test_agentic_audio.py + scripts/test_visual_routing.py + scripts/test_demo_flow.py + scripts/test_open_chat.py
verified_at: 2026-08-24 02:22 SGT
evidence: |
  You: Turn toward the port side and report the scene from there.
  Gemma: Turning to the port side shows a desk with various items like a monitor and some boxes. There is a pink object and some papers on the desk.
  dependent_tools: PASS; action=look_left_and_inspect; frame=/home/iputra/gemma-companion/captures/companion/capture-77f08ff2b20e4875a304052ba3931d30.jpg; latency_seconds=4.289
  available_memory_mib: 2498.4; limit: >500
  result: PASS Gemma semantically selects and chains embodied tools
fallback_taken: none
commit: a37eddf
notes: `parse_intent`, exact visual-phrase lists, direction aliases, and the deictic code router were removed. Every transcript now reaches Gemma's 12-capability function gate; a small model-driven completion check composes movement with fresh vision, a model-driven evidence classifier protects current physical referents, and a bounded repair turn recovers narrated tool intent. The strict llama.cpp PEG parser is bypassed, while only supplied function names and validated arguments can execute. Thirteen unfamiliar action paraphrases, three unique fresh-reference frames, the five-beat physical flow, and five unrelated open-chat questions all passed. No GitHub push was performed per the human's instruction.

## M16 Native Gemma audio experiment
status: DONE
verified_by: scripts/experiment_direct_audio.py
verified_at: 2026-08-24 02:16 SGT
evidence: |
  isolated_slots: PASS; count=1
  direct_audio_tool: PASS; tool=find_object; latency_seconds=2.524; available_memory_mib=2887.7
  result: PASS native Gemma audio selected a tool without Whisper
  IMPORTANT: restart the normal two-slot llama.cpp server before any vision request
fallback_taken: Whisper remains the stage default because native audio followed by GPU vision exhausts CUDA memory on the 8 GB Jetson; the CPU-projector alternative missed the vision latency target.
commit: a37eddf
notes: Gemma directly consumed the real `Find my glasses` WAV and selected `find_object` without transcription. The experiment is preserved behind an explicit direct-audio code path and a one-slot verifier, but it is not presented as production-ready. The normal two-slot GPU-vision server was restored afterward and `scripts/test_gemma.py` passed text, image, and tool calls with 2.6 GiB available. No GitHub push was performed.

## M17 Continuous-path latency and resilience
status: DONE
verified_by: scripts/test_companion.py + scripts/test_fast_stt.py + scripts/test_tts.py + scripts/test_playback_interrupt.py
verified_at: 2026-08-24 02:22 SGT
evidence: |
  agentic_moves: PASS; paraphrase_sequence=look_left,look_right,look_center; max_latency_seconds=2.139
  fresh_vision: PASS; direction=center; latency_seconds=4.871; response=The scene shows a desk with a computer monitor, a cardboard box, and several items like a phone and some bottles. There is also a tube of cream and some other miscellaneous objects on the surface.
  fresh_frame: /home/iputra/gemma-companion/captures/companion/capture-f5b7548046a44302b4c64be7fc9c6060.jpg
  available_memory_mib: 2505.7
  result: PASS phrase-free agent routing, physical PTZ, and fresh vision
fallback_taken: none
commit: 91ba508
notes: Tool routing now keeps prior spoken confirmations out of the physical decision prompt, restoring llama.cpp prefix-cache reuse and preventing style imitation. Relative to the pre-optimization accepted run, maximum text-to-PTZ latency fell from 2.976 to 2.139 seconds and fresh vision from 6.001 to 4.871 seconds. Neutral-prompt Whisper transcribed `Find my glasses` in 1.454--1.470 seconds; Kokoro at speed 1.08 passed with 1.311-second first audio, 2.979-second warm synthesis, 0.005-second cached start, and 2.114 GiB free even with a duplicate verifier instance; active ALSA playback cancelled in 0.0155 seconds. The boot verifier now finds the active `microphone=true` service log even after foreground tests create newer logs, and passed with Gemma/Whisper HTTP 200. The installed boot service still needs the required human-authorized restart to load the new companion process image.

## M18 Finder identity grounding
status: DONE
verified_by: scripts/test_finder_evidence.py + scripts/test_live_finder.py
verified_at: 2026-08-24 09:32 SGT
evidence: |
  airpods_positive: PASS; direction=right; location=near a table; duration_seconds=22.589
  absent_negative: PASS; target=bright magenta stapler; duration_seconds=31.807
  coverage_moves: look_left,look_right,look_up,look_down
  logs: positive=/home/iputra/gemma-companion/logs/session-20260824-092855-727643.jsonl; negative=/home/iputra/gemma-companion/logs/session-20260824-092918-386368.jsonl
  result: PASS live AirPods detection and complete honest physical sweep
fallback_taken: none
commit: 06eadd3
notes: The live service exposed an actual false positive: a magnified edge crop labeled a white cable or plastic fragment as AirPods, while its target-blind description did not support that identity. Edge-only detections now require a compact target-blind inventory plus an exact semantic identity verdict; contextual full-frame detections remain usable. The exact false-positive frame was rejected 3/3, a known genuine AirPods frame was accepted 3/3, and the live sweep rejected the cable at center before Gemma moved and found the real case. The phrase-free agent, compound vision, demo flow, arbitrary visible-reference routing, and five unfamiliar open-chat questions also passed. The service was subsequently restarted and the grounded boot verifier passed with PID 59909. The earlier no-push constraint was later superseded by the human's explicit request to publish `main`.

## M19 Public setup and portable boot service
status: DONE
verified_by: scripts/install_boot_service.sh --dry-run + scripts/test_boot_service.sh + git ls-remote
verified_at: 2026-08-24 09:43 SGT
evidence: |
  installer_render: PASS; user=iputra; group=iputra; repo=/home/iputra/gemma-companion; environment_file=/etc/default/gemma-companion
  repository_validation: PASS; readme_local_links=all; shellcheck=clean; systemd_unit=valid
  boot_service: PASS; main_pid=59909; gemma_http=200; whisper_http=200; grounded_readiness=yes
  remote_main: PASS; sha=71c2bade96569c77a98289fe3eeda0774123801a; branch=main
  result: PASS publishable setup guide, portable service installer, live boot, and remote main
fallback_taken: none
commit: 71c2bad
notes: README now takes a new JetPack 6 owner from apt prerequisites through hardware reconnaissance, pinned runtime/model bootstrap, layered verification, foreground use, automatic boot, environment overrides, updates, and troubleshooting. The installer no longer assumes the `iputra` account or `/home/iputra/gemma-companion`; it renders the invoking user, primary group, and clone path, offers a non-mutating dry run, accepts an explicit service user, and loads optional `/etc/default/gemma-companion` overrides. Real-user and alternate-user renders passed on the Jetson, documented packages resolve, every local README link exists, the unit passes `systemd-analyze verify`, and the first public push fast-forwarded `origin/main` from 33ffe4a to 71c2bad.
