import logging
import os
from datetime import datetime


class Logger:
    def __init__(self, log_file=None):
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"price_updater_{timestamp}.log"

        self.log_file = log_file

        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

        self.logger = logging.getLogger(__name__)

    def info(self, message):
        """Log de informação"""
        self.logger.info(message)

    def error(self, message):
        """Log de erro"""
        self.logger.error(message)

    def warning(self, message):
        """Log de aviso"""
        self.logger.warning(message)

    def debug(self, message):
        """Log de debug"""
        self.logger.debug(message)