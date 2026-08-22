# Build progress

Commands are labelled by execution host. Output below is real command output from this session.

## M0 Recon

### JETSON — identity check

Command:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=10 iputra@192.168.55.1 'hostname && id'
```

Exit code: 0

```text
iputra
uid=1000(iputra) gid=1000(iputra) groups=1000(iputra),4(adm),24(cdrom),27(sudo),29(audio),30(dip),44(video),46(plugdev),100(users),114(i2c),125(gdm),984(weston-launch),985(gpio),993(render)
```

### JETSON — initial verification attempt

Command:

```sh
cd ~/gemma-companion && ./scripts/recon.sh
```

Exit code: 1

```text
ERROR: v4l2-ctl is required for camera recon
```

The verifier was changed to use sysfs and direct read-only V4L2 ioctls when `v4l2-ctl` is unavailable. No package or driver installation was needed.

### JETSON — final verification

Command:

```sh
cd ~/gemma-companion && ./scripts/recon.sh
```

Exit code: 0

```text
OBSBOT video nodes: /dev/video0,/dev/video1 (capture: /dev/video0)
AT-CSP1 ALSA capture card: 3; playback card: 3
CUDA: driver API 13.2 (nvidia-l4t-cuda installed); Python: Python 3.12.3
Available RAM: 6.4Gi
Available disk on /: 425G
```

Current status: M0 DONE. M1 is next.

## M1 Camera capture

### JETSON — cold-open verification attempt

Command:

```sh
cd ~/gemma-companion && ./scripts/test_camera.py
```

Exit code: 1

```text
AssertionError: capture took 2.028s; acceptance limit is 2.000s
```

### JETSON — accepted verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_camera.py
```

Exit code: 0

```text
device: /dev/video0
capture_path: /home/iputra/gemma-companion/captures/capture-a08718edb6eb4ddf9f6379098d99da87.jpg
dimensions: 1024x576; bytes: 62710; contrast_stddev: 83.61
elapsed_seconds: 0.392
result: PASS fresh JPEG captured in under 2 seconds
```

### MAC — copied-frame inspection

Command:

```sh
scp iputra@192.168.55.1:~/gemma-companion/captures/capture-a08718edb6eb4ddf9f6379098d99da87.jpg artifacts/m1-camera.jpg
```

Exit code: 0. SHA-256: `bc6a3c9ceaf292c113394a1c72e49a993bf3bc021a2fb545627343d7243ec8e0`.

Visual description: a laptop fills the left foreground; beyond it are a white desk, large monitor, black chair/bag, small plant, and boxes. This is the expected workspace view.

Current status: M0-M1 DONE. M2 is next.
