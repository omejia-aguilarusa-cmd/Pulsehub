from loguru import logger
import sys


def setup_logging(level: str = "INFO") -> None:
    logger.remove()
    # Structured, terse logs
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}",
    )


__all__ = ["logger", "setup_logging"]

