"""Logging configuration for ASA Autopilot."""

import logging
import logging.handlers
import os


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for dry-run and production modes.

    Args:
        log_level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR').
    """
    log_dir = "/Users/rredondo/asa-autopilot/logs"
    os.makedirs(log_dir, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))

    # Guard against duplicate handlers (important for Streamlit reruns)
    if root_logger.handlers:
        return  # Handlers already configured, exit early

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "autopilot.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(getattr(logging, log_level))
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
