import logging

from shared.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Processor starting — Gemini key present: %s", bool(settings.gemini_api_key))
    # TODO: read unclassified documents from MongoDB,
    #       call Gemini for sentiment/stance classification,
    #       write ClassifiedDocument records to PostgreSQL
    raise NotImplementedError


if __name__ == "__main__":
    main()
