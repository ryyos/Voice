import time

from shared.utils import log
from processor.cleaner import Cleaner
from processor.ai import AIWorker


def main() -> None:
    """
    Processor loop — runs continuously:
      1. Cleaner  : MongoDB raw_documents → parse → PostgreSQL warehouse
      2. AI worker: PostgreSQL unprocessed comments → classify → update sentiment

    Both stages run sequentially in one loop iteration, then sleep before the next.
    """
    log.info("[ PROCESSOR ] starting — cleaner + AI worker")

    cleaner   = Cleaner()
    ai_worker = AIWorker()

    while True:
        cleaned = cleaner.run()
        log.info("[ PROCESSOR ] cleaner pass complete — {} rows", cleaned)

        try:
            classified = ai_worker.run()
            log.info("[ PROCESSOR ] AI pass complete — {} rows", classified)
        except NotImplementedError:
            log.warning("[ PROCESSOR ] AI worker not yet implemented — skipping")

        time.sleep(30)


if __name__ == "__main__":
    main()
