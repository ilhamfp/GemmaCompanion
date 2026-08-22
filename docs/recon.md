# Jetson reconnaissance

Generated on: 1970-01-01 08:07:29 +0730

## Acceptance summary

- CUDA: driver API 13.2 (nvidia-l4t-cuda installed)
- Python: Python 3.12.3
- OBSBOT video nodes: /dev/video0,/dev/video1
- Selected OBSBOT capture node: /dev/video0
- Pan/tilt controls: /dev/video0: Pan, Absolute: id=0x009a0908 min=-468000 max=468000 step=3600 default=0 flags=0x00000000;Tilt, Absolute: id=0x009a0909 min=-324000 max=324000 step=3600 default=0 flags=0x00000000
- AT-CSP1 ALSA capture card: 3
- AT-CSP1 ALSA playback card: 3
- Available RAM: 6.4Gi
- Available disk on /: 425G

## Raw inventory

```text
$ hostname && id && uname -a && cat /etc/nv_tegra_release
iputra
uid=1000(iputra) gid=1000(iputra) groups=1000(iputra),4(adm),24(cdrom),27(sudo),29(audio),30(dip),44(video),46(plugdev),100(users),114(i2c),125(gdm),984(weston-launch),985(gpio),993(render)
Linux iputra 6.8.12-1021-tegra #1 SMP PREEMPT Thu Aug  6 21:56:04 PDT 2026 aarch64 aarch64 aarch64 GNU/Linux
# R39 (release), REVISION: 2.1, GCID: 46758480, BOARD: generic, EABI: aarch64, DATE: Fri Aug  7 05:54:22 AM UTC 2026
# KERNEL_VARIANT: oot
TARGET_USERSPACE_LIB_DIR=nvidia
TARGET_USERSPACE_LIB_DIR_PATH=usr/lib/aarch64-linux-gnu/nvidia
$ free -h && df -h / && nproc
               total        used        free      shared  buff/cache   available
Mem:           7.3Gi       923Mi       5.4Gi       5.0Mi       1.2Gi       6.4Gi
Swap:             0B          0B          0B
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p1  456G  8.7G  425G   2% /
6
$ nvidia-smi; ls /usr/local/cuda*; dpkg NVIDIA/CUDA/TensorRT packages
Thu Jan  1 08:07:28 1970       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.78                 Driver Version: 595.78         CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  Orin (nvgpu)                  N/A  |   N/A              N/A |                  N/A |
| N/A   N/A  N/A             N/A  /  N/A  | Not Supported          |     N/A          N/A |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+
$ python3 --version && pip3 --version
Python 3.12.3
$ command -v v4l2-ctl ffmpeg ollama arecord aplay gst-launch-1.0 docker
/usr/bin/arecord
/usr/bin/aplay
/usr/bin/gst-launch-1.0
/usr/bin/docker
$ V4L2 device inventory
v4l2-ctl: not installed; using sysfs and direct V4L2 ioctls
OBSBOT Tiny SE: OBSBOT Tiny SE 
  /dev/video0
OBSBOT Tiny SE: OBSBOT Tiny SE 
  /dev/video1
$ direct V4L2 query for /dev/video0
card=OBSBOT Tiny SE: OBSBOT Tiny SE 
capabilities=0x84a00001 device_caps=0x04200001
video_capture=yes
Pan, Absolute: id=0x009a0908 min=-468000 max=468000 step=3600 default=0 flags=0x00000000
Tilt, Absolute: id=0x009a0909 min=-324000 max=324000 step=3600 default=0 flags=0x00000000
$ direct V4L2 query for /dev/video1
card=OBSBOT Tiny SE: OBSBOT Tiny SE 
capabilities=0x84a00001 device_caps=0x04a00000
video_capture=no
Traceback (most recent call last):
  File "<stdin>", line 24, in <module>
OSError: [Errno 25] Inappropriate ioctl for device
pan/tilt controls: none exposed
$ arecord -l && aplay -l
**** List of CAPTURE Hardware Devices ****
card 1: APE [NVIDIA Jetson Orin Nano APE], device 0: fe.admaif@290f000.ADMAIF1 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 1: fe.admaif@290f000.ADMAIF2 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 2: fe.admaif@290f000.ADMAIF3 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 3: fe.admaif@290f000.ADMAIF4 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 4: fe.admaif@290f000.ADMAIF5 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 5: fe.admaif@290f000.ADMAIF6 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 6: fe.admaif@290f000.ADMAIF7 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 7: fe.admaif@290f000.ADMAIF8 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 8: fe.admaif@290f000.ADMAIF9 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 9: fe.admaif@290f000.ADMAIF10 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 10: fe.admaif@290f000.ADMAIF11 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 11: fe.admaif@290f000.ADMAIF12 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 12: fe.admaif@290f000.ADMAIF13 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 13: fe.admaif@290f000.ADMAIF14 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 14: fe.admaif@290f000.ADMAIF15 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 15: fe.admaif@290f000.ADMAIF16 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 16: fe.admaif@290f000.ADMAIF17 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 17: fe.admaif@290f000.ADMAIF18 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 18: fe.admaif@290f000.ADMAIF19 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 19: fe.admaif@290f000.ADMAIF20 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 2: SE [OBSBOT Tiny SE], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 3: Device [USB Composite Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
**** List of PLAYBACK Hardware Devices ****
card 0: HDA [NVIDIA Jetson Orin Nano HDA], device 3: HDMI 0 [HDMI 0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 0: HDA [NVIDIA Jetson Orin Nano HDA], device 7: HDMI 1 [HDMI 1]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 0: HDA [NVIDIA Jetson Orin Nano HDA], device 8: HDMI 2 [HDMI 2]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 0: HDA [NVIDIA Jetson Orin Nano HDA], device 9: HDMI 3 [HDMI 3]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 0: fe.admaif@290f000.ADMAIF1 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 1: fe.admaif@290f000.ADMAIF2 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 2: fe.admaif@290f000.ADMAIF3 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 3: fe.admaif@290f000.ADMAIF4 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 4: fe.admaif@290f000.ADMAIF5 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 5: fe.admaif@290f000.ADMAIF6 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 6: fe.admaif@290f000.ADMAIF7 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 7: fe.admaif@290f000.ADMAIF8 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 8: fe.admaif@290f000.ADMAIF9 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 9: fe.admaif@290f000.ADMAIF10 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 10: fe.admaif@290f000.ADMAIF11 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 11: fe.admaif@290f000.ADMAIF12 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 12: fe.admaif@290f000.ADMAIF13 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 13: fe.admaif@290f000.ADMAIF14 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 14: fe.admaif@290f000.ADMAIF15 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 15: fe.admaif@290f000.ADMAIF16 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 16: fe.admaif@290f000.ADMAIF17 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 17: fe.admaif@290f000.ADMAIF18 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 18: fe.admaif@290f000.ADMAIF19 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: APE [NVIDIA Jetson Orin Nano APE], device 19: fe.admaif@290f000.ADMAIF20 (*) []
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 3: Device [USB Composite Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
$ lsusb
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 002: ID 0bda:5489 Realtek Semiconductor Corp. 4-Port USB 2.0 Hub
Bus 001 Device 003: ID 13d3:3549 IMC Networks Bluetooth Radio
Bus 001 Device 004: ID 3564:feff Remo Tech Co., Ltd. OBSBOT Tiny SE
Bus 001 Device 006: ID 0909:005b Audio-Technica Corp. USB Composite Device
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 002 Device 002: ID 0bda:0489 Realtek Semiconductor Corp. 4-Port USB 3.0 Hub
```
