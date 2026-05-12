import asyncio
from src.database.manager import get_db_manager

async def main():
    db_mgr = get_db_manager()
    await db_mgr.initialize()
    db = db_mgr.db
    
    for ch_handle in ['ChartChampions', 'ECKrown']:
        ch = await db.channels.find_one({'channel_handle': ch_handle})
        if not ch:
            continue
        cid = ch['channel_id']
        title = ch.get('channel_title', '?')
        total = await db.video_metadata.count_documents({'channel_id': cid})
        completed = await db.video_metadata.count_documents({'channel_id': cid, 'transcript_status': 'completed'})
        failed = await db.video_metadata.count_documents({'channel_id': cid, 'transcript_status': 'failed'})
        pending = await db.video_metadata.count_documents({'channel_id': cid, 'transcript_status': 'pending'})
        other = total - completed - failed - pending
        print(f"@{ch_handle} ({title}): total={total} ✅={completed} ❌={failed} ⏳={pending} other={other}")
    
    # Failed video details
    print("\n=== FAILED VIDEOS ===")
    async for v in db.video_metadata.find({'transcript_status': 'failed'}):
        error = v.get('transcript_error', 'No error recorded')
        error_cat = v.get('transcript_error_category', 'N/A')
        vid_id = v.get('video_id', '?')
        title = v.get('title', '?')[:60]
        ch_id = v.get('channel_id', '?')
        # Find channel handle
        ch = await db.channels.find_one({'channel_id': ch_id})
        handle = ch.get('channel_handle', '?') if ch else '?'
        print(f'  ❌ {vid_id} | @{handle} | {title}')
        print(f'     Error [{error_cat}]: {error[:250]}')
    
    await db_mgr.close()

asyncio.run(main())
