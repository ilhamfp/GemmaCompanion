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
commit: pending
notes: v4l2-ctl is absent, so recon used read-only sysfs/direct V4L2 ioctls. Pan and tilt absolute controls are exposed on /dev/video0. Jetson wall clock is unset (1970); verified_at uses the Mac SGT clock.
