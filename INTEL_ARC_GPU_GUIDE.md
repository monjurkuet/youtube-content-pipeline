# Intel Arc GPU Setup for OpenVINO Whisper

## ✅ Quick Fix

Add to your `.env` file:

```bash
# Use Intel GPU for Whisper transcription
OPENVINO_DEVICE=GPU

# For some Intel Arc GPUs, enable Level Zero sysman
LEVEL_ZERO_ENABLE_SYSMAN=1
```

---

## 🔍 Verify GPU Detection

```bash
# Check if GPU is detected by OpenVINO
uv run python -c "
import openvino as ov
core = ov.Core()
print('Available devices:', core.available_devices)
if 'GPU' in core.available_devices:
    print('GPU:', core.get_property('GPU', 'FULL_DEVICE_NAME'))
"
```

**Expected output:**
```
Available devices: ['CPU', 'GPU']
GPU: Intel(R) Graphics [0x56a0] (dGPU)
```

---

## 🛠️ Intel Arc GPU Requirements

### **1. Linux Kernel**
Intel Arc GPUs require **kernel 6.2 or newer**:

```bash
uname -r  # Check current kernel
```

If kernel is older than 6.2, upgrade:
```bash
# Ubuntu 22.04
sudo apt install linux-generic-hwe-22.04

# Or install latest mainline kernel
```

### **2. Intel Compute Runtime (Level Zero Driver)**

Install Intel Graphics Compute Runtime:

```bash
# Add Intel repository
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
  gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] \
https://apt.repos.intel.com/oneapi all main" | \
  sudo tee /etc/apt/sources.list.d/oneAPI.list

sudo apt update

# Install compute runtime for Arc GPUs
sudo apt install intel-opencl-icd intel-level-zero-gpu level-zero-dev

# For Arc GPUs with kernel < 6.2, also install:
# sudo apt install intel-i915-dkms xpu-smi
```

### **3. Verify Driver Installation**

```bash
# Check Level Zero devices
zio level0 list devices

# Check OpenCL devices
clinfo | grep "Device Name"

# Both should show your Intel Arc GPU
```

---

## ⚙️ Environment Variables

### **For `.env` file:**

```bash
# OpenVINO device selection
OPENVINO_DEVICE=GPU

# Enable Level Zero sysman (required for some Arc GPUs)
LEVEL_ZERO_ENABLE_SYSMAN=1

# Optional: Override GPU address space (for 32-bit issues)
# OverrideGpuAddressSpace=48

# Optional: Enable debug keys
# NEOReadDebugKeys=1
```

### **Device Options:**

| Value | Description |
|-------|-------------|
| `AUTO` | Let OpenVINO choose best device (default) |
| `GPU` | Force Intel GPU |
| `CPU` | Force CPU only |
| `GPU.0` | First GPU (useful for multi-GPU) |

---

## 🧪 Test GPU Transcription

```bash
# Test with a short video
uv run python -m src.cli transcribe "https://youtube.com/watch?v=VIDEO_ID" --verbose
```

**Look for:**
```
🔄 Loading OpenVINO Whisper model: openai/whisper-base
   Device: GPU
   Cache: /home/muham/.cache/whisper_openvino
✅ Model loaded on GPU
```

---

## ❌ Troubleshooting

### **Problem: GPU not detected**

```bash
# Check if GPU is visible to OpenVINO
uv run python -c "import openvino as ov; print(ov.Core().available_devices)"

# If only CPU shows up:
# 1. Check kernel version (need 6.2+)
uname -r

# 2. Check if drivers are installed
lsmod | grep i915

# 3. Check Level Zero
zio level0 list devices
```

### **Problem: Model loads but inference fails**

Try setting explicit GPU device:

```bash
# In .env
OPENVINO_DEVICE=GPU.0
```

### **Problem: Out of memory on GPU**

Intel Arc GPUs share system memory. Try:

```bash
# Use smaller model
OPENVINO_WHISPER_MODEL=openai/whisper-tiny

# Or use CPU for large models
OPENVINO_DEVICE=CPU
```

### **Problem: Very slow GPU inference**

This might mean it's falling back to CPU. Check:

```bash
# Monitor GPU usage during transcription
intel_gpu_top  # Requires intel-gpu-tools package

# Or check if GPU is actually being used
watch -n1 'cat /sys/class/drm/card*/power/runtime_status'
```

---

## 📊 Performance Comparison

| Device | Speed (relative) | VRAM Usage | Best For |
|--------|-----------------|------------|----------|
| **Intel Arc GPU** | 3-5x faster than CPU | Shared | Long videos |
| **CPU (6-core)** | Baseline | N/A | Short videos |
| **Whisper Tiny** | 2x faster than base | Less | Quick transcription |
| **Whisper Large** | 3x slower than base | More | High accuracy |

---

## 🔗 Useful Links

- [OpenVINO GPU Documentation](https://docs.openvino.ai/2025/get-started/install-openvino/configurations/configurations-intel-gpu.html)
- [Intel Compute Runtime GitHub](https://github.com/intel/compute-runtime)
- [Intel Arc GPU Drivers](https://www.intel.com/content/www/us/en/download/785594/intel-arc-iris-xe-graphics-windows.html)
- [Level Zero Specification](https://spec.oneapi.io/level-zero/latest/index.html)

---

## 📝 Example `.env` Configuration

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline

# OpenVINO Whisper - Intel Arc GPU
OPENVINO_WHISPER_MODEL=openai/whisper-base
OPENVINO_DEVICE=GPU
OPENVINO_CACHE_DIR=~/.cache/whisper_openvino

# Intel Arc GPU specific
LEVEL_ZERO_ENABLE_SYSMAN=1
```

