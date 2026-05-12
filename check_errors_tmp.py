import asyncio
from src.database.manager import DatabaseManager

async def main():
    db = DatabaseManager()
    await db.connect()
    for vid in ['5Zi5KPgECAE', '7hpCFj-1zl8', 'pB0N29LiOv8', 'za13LoanFiE']:
        doc = await db.client.youtube_pipeline.transcripts.find_one({'video_id': vid})
        if doc and 'error' in doc:
            err = str(doc['error'])[:200]
            print(f'{vid}: {err}')
        else:
            print(f'{vid}: no error field found')
    await db.close()

asyncio.run(main())
