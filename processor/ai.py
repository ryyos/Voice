from __future__ import annotations

from shared.postgresql.functions import PG
from shared.utils.logger import log


class AIWorker:
    """
    Reads unprocessed comments from PostgreSQL, classifies sentiment,
    and updates the row with sentiment + engine + confidence.

    Classification strategy (hybrid):
      1. IndoBERT (local model) — bulk, free, no rate limit
      2. Gemini API — fallback for low-confidence or stance-complex cases

    TODO: implement IndoBERT loading and Gemini client.
    """

    CONFIDENCE_THRESHOLD = 0.75
    BATCH_SIZE = 100

    def run(self) -> int:
        """Classify all unprocessed comments. Returns number of rows updated."""
        rows = PG.fetchall(
            "SELECT id, source, source_id, content FROM comments "
            "WHERE ai_processed = FALSE AND content IS NOT NULL "
            "LIMIT %s",
            (self.BATCH_SIZE,),
        )
        if not rows:
            log.info("[ AI ] no unprocessed comments")
            return 0

        log.info("[ AI ] processing {} comments", len(rows))
        updated = 0

        for row in rows:
            result = self._classify(row["content"])
            if result:
                if PG.update_sentiment(
                    source_id=row["source_id"],
                    source=row["source"],
                    sentiment=result["sentiment"],
                    engine=result["engine"],
                    confidence=result["confidence"],
                ):
                    updated += 1

        log.info("[ AI ] done — updated {}/{}", updated, len(rows))
        return updated

    def _classify(self, text: str) -> dict | None:
        # TODO: load IndoBERT model (do this once in __init__, not per call)
        # result = indobert_model.predict(text)
        # if result.confidence >= self.CONFIDENCE_THRESHOLD:
        #     return {"sentiment": result.label, "engine": "indobert", "confidence": result.confidence}
        # else:
        #     return self._gemini_fallback(text)
        raise NotImplementedError("AI classification not yet implemented")

    def _gemini_fallback(self, text: str) -> dict | None:
        # TODO: call Gemini API for low-confidence cases
        raise NotImplementedError
