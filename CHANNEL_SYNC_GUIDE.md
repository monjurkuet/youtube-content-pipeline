# YouTube Channel Sync Guide

## 🚀 Quick Start: Complete Workflow

### **Transcribe All Videos from a Channel**

```bash
# Step 1: Add channel to tracking
uv run python -m src.cli channel add @ChartChampions

# Step 2: Sync all videos (get metadata)
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 500

# Step 3: Transcribe all pending videos (10 at a time)
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10

# Step 4: Repeat step 3 until all videos are transcribed
# Check progress:
uv run python -m src.cli channel videos @ChartChampions --status pending
```

### **Transcribe from Multiple Channels**

```bash
# Transcribe pending videos from ALL tracked channels
uv run python -m src.cli channel transcribe-pending --batch-size 10

# Transcribe from specific channel only
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10
```

### **Full Workflow Example**

```bash
# Setup (one time)
uv run python -m src.cli channel add @ChartChampions
uv run python -m src.cli channel add @ECKrown

# Sync videos
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 500
uv run python -m src.cli channel sync @ECKrown --all --max-videos 500

# Transcribe (run repeatedly until done)
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10
uv run python -m src.cli channel transcribe-pending @ECKrown --batch-size 10

# Check progress
uv run python -m src.cli channel list
uv run python -m src.cli channel videos @ChartChampions --status completed --limit 5
```

---

## 🎯 Sync Strategies

### **1. Quick Check (Daily Use)** ⚡ RECOMMENDED
Check for new videos from the last few days:

```bash
# RSS feed - gets ~15 latest videos (2 seconds)
uv run python -m src.cli channel sync @ChartChampions

# See pending videos
uv run python -m src.cli channel videos @ChartChampions --status pending
```

**Best for:** Daily checks, quick updates

---

### **2. Incremental Sync (Smart)** 🧠 RECOMMENDED FOR CATCH-UP
Only fetch metadata for NEW videos (not in database):

```bash
# Check all videos, but only download metadata for new ones
uv run python -m src.cli channel sync @ChartChampions --all --incremental

# With limit
uv run python -m src.cli channel sync @ChartChampions --all --incremental --max-videos 500
```

**How it works:**
1. Fast fetch all video IDs (~2 seconds)
2. Compare against database
3. Only download full metadata for NEW videos
4. **Saves 90%+ time** if you already have most videos

**Best for:** Catching up after being away for weeks

**Time estimates:**
| New Videos | Time Required |
|------------|--------------|
| 10 | ~15 seconds |
| 50 | ~1 minute |
| 100 | ~2 minutes |
| 500 | ~11 minutes |

---

### **3. Full Sync (Complete Refresh)** 🔄
Fetch ALL videos with full metadata:

```bash
# All videos (slow but complete)
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 2000
```

**Best for:** 
- First-time setup
- Complete data refresh
- When you want 100% metadata for all videos

**Time estimates:**
| Videos | Time Required |
|--------|--------------|
| 100 | ~2 minutes |
| 500 | ~11 minutes |
| 1,000 | ~22 minutes |
| 1,768 | ~38 minutes |

---

## 📊 Comparison

| Method | Speed | Use Case | Metadata Coverage |
|--------|-------|----------|-------------------|
| **RSS (default)** | ⚡ 2s | Daily checks | 15 videos, 100% |
| **Incremental** | 🧠 Variable | Catch-up | New videos only, 100% |
| **Full sync** | 🐌 1.3s/video | Complete refresh | All videos, 100% |

---

## 🚀 Recommended Workflow

### **Daily:**
```bash
# Quick check for new videos
uv run python -m src.cli channel sync @ChartChampions
uv run python -m src.cli channel sync @ECKrown

# Transcribe new videos
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 5
```

### **Weekly (or after being away):**
```bash
# Smart incremental sync
uv run python -m src.cli channel sync @ChartChampions --all --incremental
uv run python -m src.cli channel sync @ECKrown --all --incremental
```

### **Monthly (complete refresh):**
```bash
# Full metadata refresh
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 2000
uv run python -m src.cli channel sync @ECKrown --all --max-videos 1000
```

---

## 💡 Pro Tips

### **Run in Background (Long Syncs):**
```bash
# Incremental sync in background
nohup uv run python -m src.cli channel sync @ChartChampions --all --incremental > sync.log 2>&1 &

# Check progress
tail -f sync.log

# Check if done
ps aux | grep "channel sync"
```

### **Verify Data Quality:**
```bash
uv run python -c "
from src.database import get_db_manager
import asyncio
db = get_db_manager()
async def check():
    videos = await db.list_videos_by_channel('UCHOP_YfwdMk5hpxbugzC1wA', limit=100)
    with_dates = sum(1 for v in videos if v.get('published_at'))
    print(f'Videos with dates: {with_dates}/100 ({100*with_dates/100:.0f}%)')
asyncio.run(check())
"
```

---

## 🖥️ Intel Arc GPU Setup (Optional)

For faster transcription with Intel Arc GPUs:

### **1. Configure Environment**

Add to `.env`:
```bash
# Use Intel GPU for Whisper
OPENVINO_DEVICE=GPU

# Enable Level Zero sysman (required for some Arc GPUs)
LEVEL_ZERO_ENABLE_SYSMAN=1

# Model selection
OPENVINO_WHISPER_MODEL=openai/whisper-base
```

### **2. Verify GPU Detection**

```bash
uv run python -c "
import openvino as ov
core = ov.Core()
print('Devices:', core.available_devices)
if 'GPU' in core.available_devices:
    print('GPU:', core.get_property('GPU', 'FULL_DEVICE_NAME'))
"
```

**Expected output:**
```
Devices: ['CPU', 'GPU']
GPU: Intel(R) Graphics (dGPU)
```

### **3. Install Drivers (if GPU not detected)**

```bash
# Add Intel repository
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
  gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] \
https://apt.repos.intel.com/oneapi all main" | \
  sudo tee /etc/apt/sources.list.d/oneAPI.list

sudo apt update

# Install compute runtime
sudo apt install intel-opencl-icd intel-level-zero-gpu level-zero-dev
```

### **4. Performance**

| Audio Length | GPU Time | CPU Time | Speedup |
|--------------|----------|----------|---------|
| 10 seconds | 42s | 40s | Similar |
| 60 seconds | 46s | 49s | **7% faster** |
| 300 seconds | ~3 min | ~3.5 min | **~15% faster** |

**Note:** GPU advantage increases with:
- Longer audio files
- Larger Whisper models (e.g., `whisper-large-v3`)
- More concurrent transcriptions

See `INTEL_ARC_GPU_GUIDE.md` for detailed setup.

---

## 📊 Transcription Status Guide

### **Check Status**
```bash
# Count by status
uv run python -c "
from src.database import get_db_manager
import asyncio
db = get_db_manager()
async def stats():
    total = await db.get_video_count()
    pending = await db.get_video_count(transcript_status='pending')
    completed = await db.get_video_count(transcript_status='completed')
    failed = await db.get_video_count(transcript_status='failed')
    print(f'Total: {total}')
    print(f'Pending: {pending}')
    print(f'Completed: {completed}')
    print(f'Failed: {failed}')
asyncio.run(stats())
"
```

### **Status Meanings**

| Status | Description | Action |
|--------|-------------|--------|
| `pending` | Video synced, not transcribed | Run `transcribe-pending` |
| `completed` | Successfully transcribed | Ready to use |
| `failed` | Transcription failed | Check error, retry |

### **Retry Failed Videos**

```bash
# Mark failed videos as pending (to retry)
uv run python -c "
from src.database import get_db_manager
import asyncio
db = get_db_manager()
async def retry_failed():
    failed = await db.get_pending_transcription_videos()
    print(f'Found {len(failed)} failed videos')
    # Note: You can manually update status if needed
asyncio.run(retry_failed())
"
```
db = get_db_manager()
async def check():
    videos = await db.list_videos_by_channel('UCHOP_YfwdMk5hpxbugzC1wA', limit=100)
    with_dates = sum(1 for v in videos if v.get('published_at'))
    print(f'Videos with dates: {with_dates}/100 ({100*with_dates/100:.0f}%)')
asyncio.run(check())
"
```

### **Check What's Pending:**
```bash
# Count pending videos
uv run python -m src.cli channel videos @ChartChampions --status pending --limit 1

# Transcribe in batches
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10
```

---

## 📈 Example Scenarios

### **Scenario 1: Daily Check**
You want to check if new videos were posted overnight:
```bash
# Takes 2 seconds
uv run python -m src.cli channel sync @ChartChampions
# Gets: ~15 latest videos with full metadata
```

### **Scenario 2: Back from Vacation**
You were away for 2 weeks and want to catch up:
```bash
# Takes ~5 minutes (assuming ~200 new videos)
uv run python -m src.cli channel sync @ChartChampions --all --incremental
# Gets: Only NEW videos with full metadata
```

### **Scenario 3: First Time Setup**
Setting up tracking for a new channel:
```bash
# Takes ~40 minutes for 1,768 videos
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 2000
# Gets: ALL videos with full metadata
```

### **Scenario 4: Data Refresh**
You want to ensure all videos have complete metadata:
```bash
# Takes ~40 minutes
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 2000
# Updates: Existing videos with missing metadata
```

