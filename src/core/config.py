import os
import json
from pathlib import Path
from typing import Optional
from .models import AppConfig, EmailConfig
from .exceptions import ConfigurationError


def load_config() -> AppConfig:
    """Carrega configuração da aplicação"""

    # Carrega do arquivo de configuração se existir
    config_file = Path("assets/config/settings.json")
    config_data = {}

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)

            # Extrai configuração de e-mail
            email_config = file_config.get('email_sender', {})
            if email_config:
                config_data['email'] = EmailConfig(
                    username=email_config.get('username', ''),
                    password=email_config.get('password', ''),
                    from_addr=email_config.get('from_addr', ''),
                    to_addrs=email_config.get('to_addrs', []),
                    smtp_host=email_config.get('smtp_host', 'smtp.gmail.com'),
                    smtp_port=email_config.get('smtp_port', 465),
                    smtp_use_ssl=email_config.get('use_tls', True)
                )

            # Outras configurações
            if 'default_values' in file_config:
                config_data['default_brand'] = file_config['default_values'].get('marca_default', 'D\'Rossi')

        except Exception as e:
            raise ConfigurationError(f"Erro ao carregar configuração: {e}")

    # Sobrescreve com variáveis de ambiente se existirem
    env_overrides = {}

    # E-mail
    if os.getenv('CADASTRO_EMAIL_USERNAME'):
        if 'email' not in config_data:
            config_data['email'] = EmailConfig(
                username='', password='', from_addr='', to_addrs=[]
            )
        config_data['email'].username = os.getenv('CADASTRO_EMAIL_USERNAME')
        config_data['email'].password = os.getenv('CADASTRO_EMAIL_PASSWORD', '')
        config_data['email'].from_addr = os.getenv('CADASTRO_EMAIL_FROM', config_data['email'].username)

        to_addrs = os.getenv('CADASTRO_EMAIL_TO', '')
        if to_addrs:
            config_data['email'].to_addrs = [addr.strip() for addr in to_addrs.split(',')]

    # Outros
    if os.getenv('CADASTRO_DEFAULT_BRAND'):
        config_data['default_brand'] = os.getenv('CADASTRO_DEFAULT_BRAND')

    if os.getenv('CADASTRO_OUTPUT_DIR'):
        config_data['output_dir'] = Path(os.getenv('CADASTRO_OUTPUT_DIR'))

    return AppConfig(**config_data)


def save_config(config: AppConfig):
    """Salva configuração em arquivo"""
    config_file = Path("assets/config/settings.json")
    config_file.parent.mkdir(parents=True, exist_ok=True)

    config_dict = {
        "default_values": {
            "marca_default": config.default_brand
        }
    }

    if config.email:
        config_dict["email_sender"] = {
            "smtp_host": config.email.smtp_host,
            "smtp_port": config.email.smtp_port,
            "use_tls": config.email.smtp_use_ssl,
            "username": config.email.username,
            "password": config.email.password,
            "from_addr": config.email.from_addr,
            "to_addrs": config.email.to_addrs
        }

    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise ConfigurationError(f"Erro ao salvar configuração: {e}")