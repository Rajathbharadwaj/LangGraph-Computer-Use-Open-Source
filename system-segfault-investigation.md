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

## Recommended Tests

1. **Memory Test**: Run `memtest86+` for several hours
2. **Stress Test**: Run `stress-ng` to check CPU stability
3. **Try LTS Kernel**: Switch to `linux-lts` temporarily
4. **Try Proprietary NVIDIA**: Switch from `nvidia-open-dkms` to `nvidia-dkms`
5. **Check BIOS Settings**: Disable E-cores temporarily to test
6. **Downgrade glibc**: If possible, try older glibc

---

## Current GPU Processes
Python process using 4632MiB VRAM (likely ComfyUI or ML workload)
