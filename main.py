"""
Sistema de Cadastro Automático D'Rossi v2.1
Arquivo principal da aplicação
"""

import sys
import os
from pathlib import Path

def setup_paths():
    """Configura os caminhos para script e executável"""
    if getattr(sys, 'frozen', False):
        # ✅ EXECUTANDO COMO EXECUTÁVEL (.exe)
        application_path = Path(sys._MEIPASS)
        src_path = application_path / 'src'

        # Cria estrutura de diretórios no Documents do usuário
        user_docs = Path.home() / "Documents"
        app_dir = user_docs / "cadastro_produtos_python"

        # Cria diretórios necessários
        (app_dir / "inputs").mkdir(parents=True, exist_ok=True)
        (app_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (app_dir / "logs").mkdir(parents=True, exist_ok=True)

        # Define diretório de trabalho
        os.chdir(app_dir)

        print("🚀 Executável D'Rossi v2.1 iniciado!")
        print(f"📁 Diretório de trabalho: {app_dir}")
        print(f"📁 Caminho da aplicação: {application_path}")
        print(f"📁 Caminho do src: {src_path}")
        print(f"📂 Src existe? {src_path.exists()}")
        print(f"📂 Inputs: {app_dir / 'inputs'}")
        print(f"📂 Outputs: {app_dir / 'outputs'}")
        print(f"📂 Logs: {app_dir / 'logs'}")
        print()

        return src_path.parent  # Retorna o diretório pai do src

    else:
        # ✅ EXECUTANDO COMO SCRIPT PYTHON
        application_path = Path(__file__).parent
        print("🐍 Executando como script Python")
        return application_path

def main():
    """Função principal da aplicação"""
    try:
        # Configura caminhos
        project_root = setup_paths()

        # ✅ ADICIONA O DIRETÓRIO DO PROJETO AO PATH (não o src)
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Verifica se o diretório src existe
        src_path = project_root / "src"
        if not src_path.exists():
            raise FileNotFoundError(f"Diretório src não encontrado: {src_path}")

        # ✅ CORREÇÃO: IMPORTAR A CLASSE MainWindow E EXECUTAR
        from src.ui.main_window import MainWindow

        print("✅ Módulos carregados com sucesso")
        print("🎯 Iniciando interface gráfica...")

        # Criar e executar aplicação
        app = MainWindow()
        app.run()

    except ImportError as e:
        error_msg = f"❌ Erro de importação: {e}"
        print(error_msg)
        print("🔧 Verifique se todos os módulos estão instalados corretamente.")
        print("📋 Execute: pip install -r requirements.txt")

        # Mostra traceback para debug
        import traceback
        traceback.print_exc()

        # Se for executável, mostra janela de erro
        if getattr(sys, 'frozen', False):
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "Erro de Importação",
                    f"{error_msg}\n\nVerifique se todos os módulos estão instalados."
                )
            except Exception:
                input("Pressione Enter para sair...")

        sys.exit(1)

    except FileNotFoundError as e:
        error_msg = f"❌ Arquivo não encontrado: {e}"
        print(error_msg)

        if getattr(sys, 'frozen', False):
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Erro de Arquivo", error_msg)
            except Exception:
                input("Pressione Enter para sair...")

        sys.exit(1)

    except Exception as e:
        error_msg = f"❌ Erro inesperado: {e}"
        print(error_msg)

        # Mostra traceback completo para debug
        import traceback
        traceback.print_exc()

        if getattr(sys, 'frozen', False):
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "Erro Inesperado",
                    f"{error_msg}\n\nVerifique os logs para mais detalhes."
                )
            except Exception:
                input("Pressione Enter para sair...")

        sys.exit(1)

if __name__ == "__main__":
    main()