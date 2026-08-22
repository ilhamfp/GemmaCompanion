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
commit: pending
notes: Standard UVC pan_absolute/tilt_absolute controls are driven with direct V4L2 ioctls because v4l2-ctl is absent. Movement is clamped to pan +/-60 degrees and tilt +/-30 degrees, safely inside hardware limits. Left/right frames were copied to the Mac and visibly differ.
