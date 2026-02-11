"""Gerenciador de recursos embarcados no executável"""

import sys
from pathlib import Path
import tempfile
import shutil

def get_resource_path(relative_path: str) -> Path:
    """
    Obtém o caminho para um recurso embarcado.
    Funciona tanto em desenvolvimento quanto no executável.
    """
    try:
        # PyInstaller cria uma pasta temporária e armazena o caminho em _MEIPASS
        base_path = Path(sys._MEIPASS)
        print(f"🔧 Modo executável detectado: {base_path}")
    except AttributeError:
        # Modo desenvolvimento - usar caminho relativo ao arquivo atual
        base_path = Path(__file__).parent.parent
        print(f"�� Modo desenvolvimento detectado: {base_path}")

    resource_path = base_path / relative_path
    print(f"📁 Caminho do recurso: {resource_path}")
    return resource_path

def extract_template_to_temp() -> Path:
    """
    Extrai a planilha modelo para um arquivo temporário.
    Retorna o caminho do arquivo temporário.
    """
    template_resource = get_resource_path("resources/templates/Planilha Destino.xlsx")

    if not template_resource.exists():
        raise FileNotFoundError(f"Template não encontrado: {template_resource}")

    # Criar diretório temporário específico para o app
    temp_dir = Path(tempfile.gettempdir()) / "cadastro_produtos_temp"
    temp_dir.mkdir(exist_ok=True)

    temp_template = temp_dir / "Planilha Destino.xlsx"

    # Copiar template para arquivo temporário
    shutil.copy2(template_resource, temp_template)
    print(f"📋 Template extraído para: {temp_template}")

    return temp_template

def get_template_path() -> Path:
    """
    Retorna o caminho da planilha modelo.
    Em desenvolvimento: caminho direto
    No executável: extrai para temp e retorna caminho temp
    """
    try:
        # Verificar se estamos no executável PyInstaller
        if hasattr(sys, '_MEIPASS'):
            print("🚀 Executável detectado - extraindo template...")
            return extract_template_to_temp()
        else:
            # Modo desenvolvimento - usar caminho direto
            print("�� Modo desenvolvimento - usando template local...")
            template_path = get_resource_path("resources/templates/Planilha Destino.xlsx")

            if not template_path.exists():
                raise FileNotFoundError(f"Template não encontrado em desenvolvimento: {template_path}")

            return template_path

    except Exception as e:
        print(f"❌ Erro ao obter template: {e}")
        raise RuntimeError(f"Erro ao obter template: {e}")

def cleanup_temp_files():
    """Remove arquivos temporários criados pelo app"""
    try:
        temp_dir = Path(tempfile.gettempdir()) / "cadastro_produtos_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print("🧹 Arquivos temporários removidos")
    except Exception as e:
        print(f"⚠️ Erro ao limpar arquivos temporários: {e}")