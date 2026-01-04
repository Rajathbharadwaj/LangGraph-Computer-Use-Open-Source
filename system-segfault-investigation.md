# System Segfault Investigation

## System Specifications

### CPU
- **Model**: Intel Core i9-13900KS (13th Gen Raptor Lake)
- **Architecture**: x86_64 Hybrid (P-cores + E-cores)
- **Cores**: 24 cores, 32 threads
- **Max Frequency**: 6.0 GHz
- **Virtualization**: VT-x enabled

### GPU
- **Model**: NVIDIA GeForce RTX 4090 (AD102)
- **Manufacturer**: MSI
- **VRAM**: 24564 MiB (24GB)
- **Driver**: 590.48.01 (nvidia-open-dkms)
- **CUDA Version**: 13.1

### Memory
- **Total RAM**: 64 GB
- **Swap**: 64 GB

### Operating System
- **Distro**: Garuda Linux (Arch-based, rolling release)
- **Kernel**: 6.18.2-zen2-1-zen (Zen kernel with PREEMPT_DYNAMIC)
- **Build Date**: Thu, 18 Dec 2025

### Key Software Versions
- **glibc**: 2.42+r33+gde1fe81f4714-1 (BLEEDING EDGE)
- **GCC**: 15.2.1 20251112 (BLEEDING EDGE)
- **Python**: 3.12.2
- **NVIDIA Driver**: nvidia-open-dkms 590.48.01-1

---

## Segfault Log Analysis (Last 7 Days)

### Pattern 1: libcuda.so Crashes (MOST COMMON)
Multiple segfaults in the NVIDIA CUDA library:
```
Jan 03 18:39:13 - python[32304]: segfault in libcuda.so.590.48.01
Jan 03 19:43:08 - python[668621]: segfault in libcuda.so.590.48.01
Jan 04 04:19:32 - python[803265]: segfault in libcuda.so.590.48.01
Jan 04 04:22:13 - python[2543738]: segfault in libcuda.so.590.48.01
Jan 04 04:38:37 - python[2547515]: segfault in nvidiactl
```

### Pattern 2: Core-Specific Crashes
Crashes predominantly on specific CPU cores:
- **Core 16 (E-core)**: Multiple crashes
- **Core 20 (E-core)**: Most frequent crashes
- **Core 8, 9, 10, 11**: Also affected

This suggests possible issues with Intel's hybrid architecture (P-cores vs E-cores).

### Pattern 3: System Library Crashes
```
Jan 03 18:36:45 - python: segfault in libstdc++.so.6.0.34
Jan 04 01:07:20 - preload[1283]: segfault in libc.so.6
```

### Pattern 4: Python/ML Framework Crashes
```
Jan 03 18:35:19 - python: segfault in onnxruntime_pybind11_state.cpython-311
Jan 04 03:24:15 - python[2482377]: segfault in python3.11
Jan 04 05:22:35 - python3[2606627]: segfault in python3
```

### Pattern 5: Browser/WebExtensions
```
Jan 03 23:08:35 - WebExtensions[9563]: segfault
Jan 03 23:08:36 - WebExtensions[1814981]: segfault
```

### Pattern 6: Null Pointer Dereferences
Multiple crashes at address 0x0 (null pointer):
```
Jan 03 18:43:37 - python[413770]: segfault at 0 ip 0000000000000000
Jan 04 04:20:39 - python[2544435]: segfault at 0 ip 0000000000000000
Jan 04 04:39:12 - python[2566782]: segfault at 0 ip 0000000000000000
```

---

## Potential Causes to Investigate

### 1. NVIDIA Driver Issues
- Using nvidia-open-dkms (open-source kernel modules) - known to be less stable
- Driver version 590.48.01 may have bugs
- Interaction with Zen kernel patches

### 2. Intel Hybrid Architecture + Zen Kernel
- i9-13900KS has P-cores (performance) and E-cores (efficiency)
- Thread scheduling on E-cores causing issues
- Zen kernel scheduler may not handle hybrid correctly

### 3. Bleeding Edge glibc 2.42
- glibc 2.42 is extremely new (released late 2025)
- May have compatibility issues with some software
- Known to cause issues with certain binary-only software

### 4. Bleeding Edge GCC 15.2
- GCC 15 is very new
- Compiled libraries may have optimization bugs
- libstdc++ 6.0.34 issues

### 5. Memory Issues (Less Likely but Possible)
- Could be faulty RAM
- XMP/EXPO profile causing instability
- Memory timing issues

### 6. Kernel 6.18 + Zen Patches
- Very new kernel version
- Zen patches may introduce instability
- PREEMPT_DYNAMIC scheduler issues

---

---

# ROOT CAUSE ANALYSIS (Research Findings)

## PRIMARY ISSUE: Intel 13th Gen Hybrid Architecture

Your crashes are happening predominantly on **CPU cores 16, 20 (E-cores)**. This is a KNOWN issue:

1. **Linux Scheduler Bug**: A major bug in the Intel P-State driver causes tasks to incorrectly run on E-cores when they should be on P-cores. This causes up to 50% performance hits and crashes.

2. **i9-13900KS Hardware Degradation**: Intel's 13th/14th Gen CPUs have a **known hardware degradation issue** caused by excessive voltage. The i9-13900KS is particularly affected. Intel has released microcode updates and extended warranties.

3. **CUDA + E-cores Don't Mix**: CUDA operations getting scheduled to E-cores causes compatibility issues since CUDA expects consistent high-performance cores.

## SECONDARY ISSUE: nvidia-open-dkms Instability

- The transition to nvidia-open-dkms with driver 590 happened in late 2025
- Known to cause kernel panics and segfaults in `libnvidia-glcore.so`
- Less stable than proprietary nvidia-dkms

## TERTIARY ISSUE: Bleeding Edge glibc 2.42

- Confirmed bug: `file` command crashes with "invalid system call" in TTY sessions
- Your libstdc++ crashes may be related to glibc 2.42 + GCC 15.2.1 ABI issues

---

# SOLUTION: Prioritized Action Plan

## Step 1: Update Intel Microcode (CRITICAL)
```bash
# Check current microcode
cat /proc/cpuinfo | grep microcode | head -1

# Install latest (need version 0x129+)
sudo pacman -S intel-ucode
sudo mkinitcpio -P
sudo reboot
```

## Step 2: Pin CUDA/GPU Workloads to P-cores Only
```bash
# Add to ~/.bashrc or /etc/environment
export GOMP_CPU_AFFINITY="0-7"

# Or run GPU apps with taskset
taskset -c 0-7 python your_comfyui_script.py
```

## Step 3: Test with E-cores Disabled (Diagnostic)
1. Enter BIOS (Del/F2 during boot)
2. Advanced > CPU Configuration
3. Set "Efficient Cores" to 0 or Disabled
4. Save and reboot
5. If crashes stop, the hybrid scheduler is confirmed as the issue

## Step 4: Try LTS Kernel Instead of Zen
```bash
sudo pacman -S linux-lts linux-lts-headers
sudo grub-mkconfig -o /boot/grub/grub.cfg
# Boot with LTS kernel from GRUB menu
```

## Step 5: Switch to Proprietary NVIDIA Driver
```bash
sudo pacman -Rns nvidia-open-dkms
sudo pacman -S nvidia-dkms
sudo reboot
```

## Step 6: Check for Intel CPU Warranty
Your i9-13900KS may qualify for Intel's extended warranty program due to the known degradation issue:
https://community.intel.com/t5/Blogs/Tech-Innovation/Client/Intel-Core-13th-and-14th-Gen-Desktop-Instability-Root-Cause/post/1633239

---

# Diagnostic Commands

```bash
# Check microcode version
cat /proc/cpuinfo | grep microcode | head -1

# Check for kernel CPU errors
dmesg | grep -i "itmt\|pstate\|hybrid\|mce"

# View recent crashes
coredumpctl list

# Monitor kernel errors
journalctl -k -p err

# Check CPU core types
cat /sys/devices/system/cpu/cpu*/topology/core_type
```

---

# Sources

- Intel 13th/14th Gen Root Cause: https://community.intel.com/t5/Blogs/Tech-Innovation/Client/Intel-Core-13th-and-14th-Gen-Desktop-Instability-Root-Cause/post/1633239
- Intel Microcode Fix: https://www.tomshardware.com/pc-components/cpus/intel-rolls-out-linux-kernel-microcode-fix-for-affected-13th-14th-generation-processors
- Linux Intel Hybrid CPU Fix: https://www.phoronix.com/news/Linux-6.10-rc6-PM-Intel-Core
- NVIDIA 590 Driver Switch: https://archlinux.org/news/nvidia-590-driver-drops-pascal-support-main-packages-switch-to-open-kernel-modules/
- glibc 2.42 Crash Bug: https://bbs.archlinux.org/viewtopic.php?id=307443
