import sys
import logging
import logging.handlers

from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

NOISY_LOGGERS = ("aiormq", "aio_pika", "asyncio", "httpcore")

_HANDLER_MARK = "_payment_processing_handler"


def configure_logging(
    level: str | int = logging.INFO,
    log_file: str | Path | None = "logs/app.log",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    console_level: str | int = logging.INFO,
) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    for handler in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(formatter)
    _add_handler(root, console)

    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        _add_handler(root, file_handler)

    if root.getEffectiveLevel() < logging.INFO:
        for name in NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)


def _add_handler(root: logging.Logger, handler: logging.Handler) -> None:
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
