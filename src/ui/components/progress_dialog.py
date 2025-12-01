"""Diálogo de progresso"""

import customtkinter as ctk
import tkinter as tk


class ProgressDialog:
    """Diálogo modal de progresso"""

    def __init__(self, parent):
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        """Configura interface do diálogo"""
        # Janela modal
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Processando...")
        self.window.geometry("400x200")
        self.window.resizable(False, False)

        # Centraliza na tela
        self.window.transient(self.parent)

        # Centralizar
        self.center_window()

        # Conteúdo
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="🔄 Processando Planilha",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 10))

        # Status
        self.status_var = tk.StringVar(value="Iniciando processamento...")
        self.status_label = ctk.CTkLabel(
            main_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=12),
            wraplength=350
        )
        self.status_label.pack(pady=(0, 20))

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(
            main_frame,
            variable=self.progress_var,
            height=20
        )
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 10))

        # Porcentagem
        self.percent_var = tk.StringVar(value="0%")
        self.percent_label = ctk.CTkLabel(
            main_frame,
            textvariable=self.percent_var,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.percent_label.pack(pady=(0, 20))

    def center_window(self):
        """Centraliza janela na tela"""
        self.window.update_idletasks()

        # Dimensões da janela
        width = self.window.winfo_width()
        height = self.window.winfo_height()

        # Dimensões da tela
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        # Calcula posição central
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def update_progress(self, value: float):
        """Atualiza progresso (0.0 a 1.0)"""
        self.progress_var.set(value)
        self.percent_var.set(f"{value * 100:.0f}%")

    def update_status(self, message: str):
        """Atualiza mensagem de status"""
        self.status_var.set(message)

    def destroy(self):
        """Fecha diálogo"""
        if self.window:
            self.window.destroy()