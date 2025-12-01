"""Diálogo para seleção entre gerenciador de produtos e catálogo"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ProductSelectionDialog:
    """Diálogo para escolher entre produtos/componentes e catálogo"""

    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        self.result = None

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("🛋️ Gerenciamento de Produtos")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Criar widgets
        self.create_widgets()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 600) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"600x500+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="🛋️ Gerenciamento de Produtos",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(30, 20))

        subtitle_label = ctk.CTkLabel(
            main_frame,
            text="Escolha qual sistema deseja acessar:",
            font=ctk.CTkFont(size=14)
        )
        subtitle_label.pack(pady=(0, 40))

        # Container para opções
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.pack(fill="both", expand=True, padx=20)

        # Opção 1: Produtos e Componentes
        self.create_option_card(
            options_frame,
            "🔧 Produtos e Componentes",
            "Gerenciar produtos por partes (assentos + pés/bases)\n"
            "• Importar planilha de componentes\n"
            "• Gerenciar assentos e pés/bases separadamente\n"
            "• Gerar combinações automáticas\n"
            "• Ideal para montagem de produtos",
            self.open_components_manager,
            "left"
        )

        # Opção 2: Catálogo de Produtos
        self.create_option_card(
            options_frame,
            "📋 Catálogo de Produtos",
            "Gerenciar catálogo completo de produtos finais\n"
            "• Importar planilha do catálogo\n"
            "• Produtos com todas as informações\n"
            "• Busca avançada e filtros\n"
            "• Ideal para catálogo e vendas",
            self.open_catalog_manager,
            "right"
        )

        # Botão fechar
        ctk.CTkButton(
            main_frame,
            text="❌ Fechar",
            command=self.close_dialog,
            width=120,
            height=35
        ).pack(pady=(30, 20))

    def create_option_card(self, parent, title, description, command, side):
        """Cria um card de opção"""
        # Frame do card
        card_frame = ctk.CTkFrame(parent)
        if side == "left":
            card_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        else:
            card_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # Título do card
        title_label = ctk.CTkLabel(
            card_frame,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(30, 20))

        # Descrição
        desc_label = ctk.CTkLabel(
            card_frame,
            text=description,
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=250
        )
        desc_label.pack(pady=(0, 30), padx=20)

        # Botão
        button_text = "🔧 Abrir" if side == "left" else "📋 Abrir"
        ctk.CTkButton(
            card_frame,
            text=button_text,
            command=command,
            width=150,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(0, 30))

    def open_components_manager(self):
        """Abre gerenciador de componentes"""
        try:
            from .product_manager_window import ProductManagerWindow

            # Definir caminho do banco de produtos
            products_db_path = self.config.output_dir / "products.db"

            ProductManagerWindow(self.parent, products_db_path)
            self.result = "components"
            self.dialog.destroy()

        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de componentes: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador:\n{e}")

    def open_catalog_manager(self):
        """Abre gerenciador de catálogo"""
        try:
            from .catalog_manager_window import CatalogManagerWindow

            # Definir caminho do banco do catálogo
            catalog_db_path = self.config.output_dir / "product_catalog.db"

            CatalogManagerWindow(self.parent, catalog_db_path)
            self.result = "catalog"
            self.dialog.destroy()

        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de catálogo: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador:\n{e}")

    def close_dialog(self):
        """Fecha o diálogo"""
        self.dialog.destroy()