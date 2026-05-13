import asyncio
import time

from app.core.database import SessionLocal, init_db
from app.models import ScanJob
from app.models.entities import ScanStatus
from app.services.crawler import CompanyCrawler


async def tick() -> None:
    init_db()
    while True:
        db = SessionLocal()
        try:
            scan = db.query(ScanJob).filter(ScanJob.status == ScanStatus.queued).order_by(ScanJob.created_at).first()
            if scan:
                await CompanyCrawler(db).run_scan(scan.id)
            else:
                await asyncio.sleep(3)
        finally:
            db.close()
        time.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(tick())

