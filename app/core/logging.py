import logging
import sys


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # The ES transport logs every request at INFO, which is too noisy.
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)
