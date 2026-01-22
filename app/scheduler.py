import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger("scheduler")

class QueryScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone="Europe/Rome")

    def add_job(self, fn, seconds: int, job_id: str):
        log.info("Adding job %s every %ss", job_id, seconds)
        self.scheduler.add_job(
            fn,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def start(self):
        log.info("Starting APScheduler")
        self.scheduler.start()

    def block_forever(self):
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Stopping scheduler")
            self.scheduler.shutdown(wait=False)
