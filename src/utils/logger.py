import sys
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.logging import RichHandler

# Console para output colorido
console = Console()


def setup_logger(log_level: str = "INFO", log_file: bool = True):
    """Configura o sistema de logging"""

    # Remove handlers padrão
    logger.remove()

    # Handler para console com Rich
    logger.add(
        RichHandler(console=console, rich_tracebacks=True),
        level=log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # Handler para arquivo se solicitado
    if log_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        logger.add(
            log_dir / "cadastro_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="1 day",
            retention="30 days",
            compression="zip"
        )

    return logger


def get_logger(name: str = None):
    """Retorna logger configurado"""
    if name:
        return logger.bind(name=name)
    return logger


# Configuração padrão
setup_logger()
