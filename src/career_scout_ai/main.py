import logging

from career_scout_ai.config import AppConfig
from career_scout_ai.scraper.portals import justjoinit, nofluffjobs
from career_scout_ai.storage.database import get_session_factory, init_db


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("data/scraper.log"),
        ],
    )
    logger = logging.getLogger(__name__)

    config = AppConfig()
    logger.info("Starting %s", config.app_name)

    engine = init_db(config.database_path)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        for portal in (justjoinit, nofluffjobs):
            run = portal.scrape(session)
            logger.info(
                "[%s] Run #%d: found=%d new=%d status=%s",
                run.portal,
                run.id,
                run.listings_found,
                run.listings_new,
                run.status,
            )


if __name__ == "__main__":
    main()
