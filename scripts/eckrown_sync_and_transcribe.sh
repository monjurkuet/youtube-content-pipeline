#!/usr/bin/env bash
# Sync ECKrown channel and transcribe pending/missing videos
# Used by Hermes cron job: every 12h

set -euo pipefail

PROJECT_DIR="/home/administrator/githubrepo/youtube-content-pipeline"
LOG_FILE="/tmp/hermes-eckrown-cron.log"

cd "$PROJECT_DIR"

echo "============================================" >> "$LOG_FILE"
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Starting ECKrown sync + transcribe run" >> "$LOG_FILE"

# Step 0: Verify VPN proxy is available
echo "[$(date -u '+%H:%M:%S')] Checking VPN proxy... " >> "$LOG_FILE"
if timeout 5 bash -c 'echo > /dev/tcp/10.200.200.2/8888' 2>/dev/null; then
    PROXY_OK=1
    echo " OK" >> "$LOG_FILE"
else
    PROXY_OK=0
    echo " DOWN - will attempt transcription without proxy" >> "$LOG_FILE"
fi

# Step 1: Sync channel (incremental mode — only new videos)
echo "[$(date -u '+%H:%M:%S')] Syncing @ECKrown (incremental)..." >> "$LOG_FILE"
uv run python -m src.cli channel sync @ECKrown --incremental 2>&1 | tee -a "$LOG_FILE"

sleep 5

# Step 2: Find pending video IDs (transcript_status != "completed" or doesn't exist)
echo "[$(date -u '+%H:%M:%S')] Checking for pending videos..." >> "$LOG_FILE"

PENDING_JSON=$(uv run python -c "
import asyncio, os, sys
sys.path.insert(0, '$PROJECT_DIR')
os.chdir('$PROJECT_DIR')
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

async def find_pending():
    client = AsyncIOMotorClient(os.environ['MONGODB_URL'])
    db = client[os.environ.get('MONGODB_DATABASE', 'video_pipeline')]
    ch = await db['channels'].find_one({'channel_id': 'UCnwxzpFzZNtLH8NgTeAROFA'})
    if not ch:
        print('CHANNEL_NOT_FOUND')
        return
    pending = await db['video_metadata'].find(
        {'channel_id': 'UCnwxzpFzZNtLH8NgTeAROFA', 'transcript_status': {'\$ne': 'completed'}},
        sort=[('published_at', -1)]
    ).to_list(length=50)
    if not pending:
        print('ALL_DONE')
        return
    for v in pending:
        vid = v.get('video_id')
        title = (v.get('title') or '?')[:60]
        print(f'{vid}|{title}')

asyncio.run(find_pending())
" 2>/dev/null)

if [ "$PENDING_JSON" = "ALL_DONE" ]; then
    echo "[$(date -u '+%H:%M:%S')] ✅ All videos already transcribed!" >> "$LOG_FILE"
elif [ "$PENDING_JSON" = "CHANNEL_NOT_FOUND" ]; then
    echo "[$(date -u '+%H:%M:%S')] ❌ Channel not found in DB" >> "$LOG_FILE"
else
    echo "[$(date -u '+%H:%M:%S')] Found pending videos:" >> "$LOG_FILE"
    echo "$PENDING_JSON" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    # Step 3: Transcribe each pending video (handles video IDs starting with dashes)
    echo "$PENDING_JSON" | while IFS='|' read -r vid title; do
        if [ -z "$vid" ]; then continue; fi
        echo "[$(date -u '+%H:%M:%S')] Transcribing: $vid — $title" >> "$LOG_FILE"
        # Use -- to prevent leading dashes being parsed as options
        uv run python -m src.cli transcribe -- "$vid" 2>&1 | tail -8 >> "$LOG_FILE"
        echo "" >> "$LOG_FILE"
        sleep 5  # small delay between transcriptions
    done
    
    echo "[$(date -u '+%H:%M:%S')] ✅ Transcription batch complete" >> "$LOG_FILE"
fi

echo "[$(date -u '+%H:%M:%S')] EOKrown run finished" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"