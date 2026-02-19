import json
import os
from pathlib import Path


class ConfigManager:
    def __init__(self):
        self.config_file = "config.json"
        self.default_config = {
            "base_file_path": "",
            "company_name": "D'Rossi",
            "version": "1.0",
            "last_products_folder": "",
            "auto_open_result": True,
            "show_animations": True
        }
        self.config = self.load_config()

    def load_config(self):
        """Carregar configuração do arquivo"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Mesclar com configuração padrão para novos campos
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                return self.default_config.copy()
        except Exception as e:
            print(f"Erro ao carregar config: {e}")
            return self.default_config.copy()

    def save_config(self):
        """Salvar configuração no arquivo"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar config: {e}")
            return False

    def get(self, key, default=None):
        """Obter valor da configuração"""
        return self.config.get(key, default)

    def set(self, key, value):
        """Definir valor na configuração"""
        self.config[key] = value
        self.save_config()

    def get_base_file_path(self):
        """Obter caminho da planilha base"""
        return self.config.get("base_file_path", "")

    def set_base_file_path(self, path):
        """Definir caminho da planilha base"""
        self.config["base_file_path"] = path
        self.save_config()

    def is_configured(self):
        """Verificar se sistema está configurado"""
        base_path = self.get_base_file_path()
        return base_path and os.path.exists(base_path)