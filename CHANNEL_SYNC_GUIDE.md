# YouTube Channel Sync Guide

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

