"""Visualizador de logs"""

import customtkinter as ctk
import tkinter as tk
from tkinter import scrolledtext
from pathlib import Path
import threading
import time


class LogViewer:
    """Janela para visualizar logs"""

    def __init__(self, parent):
        self.parent = parent
        self.setup_ui()
        self.load_logs()

    def setup_ui(self):
        """Configura interface"""
        # Janela
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("📋 Logs do Sistema")
        self.window.geometry("800x600")

        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="📋 Logs do Sistema",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 10))

        # Botões
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="🔄 Atualizar",
            command=self.load_logs,
            width=100
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="🗑️ Limpar",
            command=self.clear_logs,
            width=100
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="📁 Abrir Pasta",
            command=self.open_log_folder,
            width=120
        ).pack(side="left")

        # Área de texto
        text_frame = ctk.CTkFrame(main_frame)
        text_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.text_area = ctk.CTkTextbox(
            text_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none"
        )
        self.text_area.pack(fill="both", expand=True, padx=10, pady=10)

    def load_logs(self):
        """Carrega logs do arquivo"""

        def load_in_thread():
            try:
                log_dir = Path("logs")
                if not log_dir.exists():
                    self.window.after(0, lambda: self.text_area.insert("1.0", "Nenhum arquivo de log encontrado.\n"))
                    return

                # Busca arquivo de log mais recente
                log_files = list(log_dir.glob("cadastro_*.log"))
                if not log_files:
                    self.window.after(0, lambda: self.text_area.insert("1.0", "Nenhum arquivo de log encontrado.\n"))
                    return

                latest_log = max(log_files, key=lambda f: f.stat().st_mtime)

                # Lê conteúdo
                with open(latest_log, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Atualiza interface na thread principal
                self.window.after(0, lambda: self.update_text_content(content))

            except Exception as e:
                error_msg = f"Erro ao carregar logs: {e}\n"
                self.window.after(0, lambda: self.text_area.insert("1.0", error_msg))

        # Limpa área de texto
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", "Carregando logs...\n")

        # Carrega em thread separada
        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()

    def update_text_content(self, content: str):
        """Atualiza conteúdo da área de texto"""
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", content)

        # Vai para o final
        self.text_area.see("end")

    def clear_logs(self):
        """Limpa área de texto"""
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", "Logs limpos.\n")

    def open_log_folder(self):
        """Abre pasta de logs"""
        import os
        import subprocess
        import platform

        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        try:
            if platform.system() == "Windows":
                os.startfile(log_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", log_dir])
            else:  # Linux
                subprocess.run(["xdg-open", log_dir])
        except Exception as e:
            tk.messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")
