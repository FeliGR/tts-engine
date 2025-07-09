"""
Logger Adapter Module

This adapter implements the ILogger interface using LoggerFactory from utils/logger.py.
It preserves all the configuration and supports lazy formatting.
"""

from config import Config
from core.interfaces.logger_interface import ILogger
from utils.logger import LoggerFactory


class LoggerAdapter(ILogger):
    """
    Logger adapter that implements the ILogger interface.

    This adapter delegates logging calls to an underlying logger instance created by LoggerFactory.
    """

    def __init__(self, name: str = "tts-service", config: object = None) -> None:
        """
        Initialize the LoggerAdapter.

        Args:
            name (str): The name of the logger.
            config (object, optional): Configuration object with logging settings.
                Defaults to the global Config if not provided.
        """
        if config is None:
            config = Config
        self._logger = LoggerFactory.get_logger(
            name=name,
            log_level=getattr(config, "LOG_LEVEL", "INFO"),
            log_to_file=getattr(config, "LOG_TO_FILE", False),
            log_file_path=getattr(config, "LOG_FILE_PATH", None),
        )

    def debug(self, message: str, *args, **kwargs) -> None:
        """
        Log a debug-level message.

        Args:
            message (str): The log message.
            *args: Additional positional arguments for the message formatting.
            **kwargs: Additional keyword arguments.
        """
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        """
        Log an info-level message.

        Args:
            message (str): The log message.
            *args: Additional positional arguments for the message formatting.
            **kwargs: Additional keyword arguments.
        """
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        """
        Log a warning-level message.

        Args:
            message (str): The log message.
            *args: Additional positional arguments for the message formatting.
            **kwargs: Additional keyword arguments.
        """
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        """
        Log an error-level message.

        Args:
            message (str): The log message.
            *args: Additional positional arguments for the message formatting.
            **kwargs: Additional keyword arguments.
        """
        self._logger.error(message, *args, **kwargs)


app_logger = LoggerAdapter()
