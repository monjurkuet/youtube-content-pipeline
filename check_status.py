import asyncio
from src.database.manager import MongoDBManager

async def check():
    db_mgr = MongoDBManager()
    await db_mgr.initialize()

    # ChartChampions (channel_id: UCHOP_YfwdMk5hpxbugzC1wA)
    cc_id = 'UCHOP_YfwdMk5hpxbugzC1wA'
    ek_id = 'UCnwxzpFzZNtLH8NgTeAROFA'

    for label, ch_id in [('ChartChampions', cc_id), ('ECKrown', ek_id)]:
        pending = await db_mgr.video_metadata.count_documents({'channel_id': ch_id, 'transcript_status': 'pending'})
        completed = await db_mgr.video_metadata.count_documents({'channel_id': ch_id, 'transcript_status': 'completed'})
        failed = await db_mgr.video_metadata.count_documents({'channel_id': ch_id, 'transcript_status': 'failed'})
        total = await db_mgr.video_metadata.count_documents({'channel_id': ch_id})
        print(f'{label}: total={total}, pending={pending}, completed={completed}, failed={failed}')

    # Get error details for failed videos
    for vid_id in ['5Zi5KPgECAE', '7hpCFj-1zl8', 'pB0N29LiOv8', 'za13LoanFiE']:
        doc = await db_mgr.video_metadata.find_one(
            {'video_id': vid_id},
            {'transcript_error': 1, 'transcript_error_category': 1, 'transcript_failure_count': 1, 'title': 1}
        )
        if doc:
            err = doc.get('transcript_error', 'N/A')
            cat = doc.get('transcript_error_category', 'N/A')
            fc = doc.get('transcript_failure_count', 0)
            title = doc.get('title', 'N/A')[:60]
            print(f'FAILED {vid_id}: [{cat}] (attempts={fc}) {title}')
            print(f'  Error: {err[:200]}')

    await db_mgr.close()

asyncio.run(check())
