"""Dashboard integrado para produtos e catálogo"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import logging
import threading

from ...core.product_database import ProductDatabase
from ...core.product_catalog_database import ProductCatalogDatabase

logger = logging.getLogger(__name__)


class ProductsDashboard:
    """Dashboard integrado para produtos e catálogo"""

    def __init__(self, parent, config):
        self.parent = parent
        self.config = config

        # ✅ CORREÇÃO: Definir caminhos dos bancos corretamente
        self.products_db_path = config.output_dir / "products.db"
        self.catalog_db_path = config.output_dir / "product_catalog.db"

        # Criar janela
        self.window = ctk.CTkToplevel(parent)
        self.window.title("📊 Dashboard de Produtos")
        self.window.geometry("1000x700")
        self.window.transient(parent)
        self.window.grab_set()

        # Centralizar
        self.center_window()

        # Criar widgets
        self.create_widgets()

        # Carregar dados
        self.load_dashboard_data()

    def center_window(self):
        """Centraliza a janela"""
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 1000) // 2
        y = (self.window.winfo_screenheight() - 700) // 2
        self.window.geometry(f"1000x700+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="📊 Dashboard de Produtos",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Container principal
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Lado esquerdo: Estatísticas
        self.create_stats_section(content_frame)

        # Lado direito: Ações rápidas
        self.create_actions_section(content_frame)

        # Botões inferiores
        self.create_bottom_buttons(main_frame)

    def create_stats_section(self, parent):
        """Cria seção de estatísticas"""
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(
            stats_frame,
            text="📈 Estatísticas dos Sistemas",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 20))

        # Produtos e Componentes
        components_frame = ctk.CTkFrame(stats_frame)
        components_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            components_frame,
            text="🔧 Produtos e Componentes",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.components_stats_var = tk.StringVar(value="Carregando...")
        self.components_stats_label = ctk.CTkLabel(
            components_frame,
            textvariable=self.components_stats_var,
            font=ctk.CTkFont(size=11),
            justify="left"
        )
        self.components_stats_label.pack(pady=(0, 15), padx=15)

        # Catálogo
        catalog_frame = ctk.CTkFrame(stats_frame)
        catalog_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            catalog_frame,
            text="📋 Catálogo de Produtos",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.catalog_stats_var = tk.StringVar(value="Carregando...")
        self.catalog_stats_label = ctk.CTkLabel(
            catalog_frame,
            textvariable=self.catalog_stats_var,
            font=ctk.CTkFont(size=11),
            justify="left"
        )
        self.catalog_stats_label.pack(pady=(0, 15), padx=15)

        # Status dos bancos
        status_frame = ctk.CTkFrame(stats_frame)
        status_frame.pack(fill="x", padx=20)

        ctk.CTkLabel(
            status_frame,
            text="💾 Status dos Bancos de Dados",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.db_status_var = tk.StringVar(value="Verificando...")
        self.db_status_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.db_status_var,
            font=ctk.CTkFont(size=11),
            justify="left"
        )
        self.db_status_label.pack(pady=(0, 15), padx=15)

    def create_actions_section(self, parent):
        """Cria seção de ações rápidas"""
        actions_frame = ctk.CTkFrame(parent)
        actions_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

        ctk.CTkLabel(
            actions_frame,
            text="⚡ Ações Rápidas",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 20))

        # Produtos e Componentes
        comp_actions_frame = ctk.CTkFrame(actions_frame)
        comp_actions_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            comp_actions_frame,
            text="🔧 Produtos e Componentes",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 15))

        ctk.CTkButton(
            comp_actions_frame,
            text="🛠️ Abrir Gerenciador",
            command=self.open_components_manager,
            width=200,
            height=35
        ).pack(pady=(0, 10))

        ctk.CTkButton(
            comp_actions_frame,
            text="📥 Importar Planilha",
            command=self.import_components,
            width=200,
            height=35
        ).pack(pady=(0, 15))

        # Catálogo
        cat_actions_frame = ctk.CTkFrame(actions_frame)
        cat_actions_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            cat_actions_frame,
            text="📋 Catálogo de Produtos",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 15))

        ctk.CTkButton(
            cat_actions_frame,
            text="📋 Abrir Catálogo",
            command=self.open_catalog_manager,
            width=200,
            height=35
        ).pack(pady=(0, 10))

        ctk.CTkButton(
            cat_actions_frame,
            text="📥 Importar Catálogo",
            command=self.import_catalog,
            width=200,
            height=35
        ).pack(pady=(0, 15))

        # Ações gerais
        general_actions_frame = ctk.CTkFrame(actions_frame)
        general_actions_frame.pack(fill="x", padx=20)

        ctk.CTkLabel(
            general_actions_frame,
            text="🔄 Ações Gerais",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 15))

        ctk.CTkButton(
            general_actions_frame,
            text="🔄 Atualizar Dashboard",
            command=self.refresh_dashboard,
            width=200,
            height=35
        ).pack(pady=(0, 10))

        ctk.CTkButton(
            general_actions_frame,
            text="🗂️ Abrir Pasta de Dados",
            command=self.open_data_folder,
            width=200,
            height=35
        ).pack(pady=(0, 15))

    def create_bottom_buttons(self, parent):
        """Cria botões inferiores"""
        bottom_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            bottom_frame,
            text="❌ Fechar",
            command=self.close_dashboard,
            width=120,
            height=35
        ).pack(side="right")

    def load_dashboard_data(self):
        """Carrega dados do dashboard"""

        def load_data():
            try:
                # Carregar estatísticas dos componentes
                try:
                    products_db = ProductDatabase(self.products_db_path)
                    comp_stats = products_db.get_stats()

                    comp_text = (
                        f"📦 Produtos: {comp_stats.get('total_produtos', 0)}\n"
                        f"🪑 Assentos: {comp_stats.get('total_assentos', 0)}\n"
                        f"🦵 Pés/Bases: {comp_stats.get('total_pes_bases', 0)}\n"
                        f"🔗 Combinações: {comp_stats.get('total_combinacoes', 0)}"
                    )

                    self.window.after(0, lambda: self.components_stats_var.set(comp_text))

                except Exception as e:
                    error_text = f"❌ Erro ao carregar:\n{str(e)[:50]}..."
                    self.window.after(0, lambda: self.components_stats_var.set(error_text))

                # Carregar estatísticas do catálogo
                try:
                    catalog_db = ProductCatalogDatabase(self.catalog_db_path)
                    cat_stats = catalog_db.get_stats()

                    cat_text = (
                        f"📋 Total de Produtos: {cat_stats.get('total_produtos', 0)}\n"
                        f"✅ Com EAN: {cat_stats.get('com_ean', 0)}\n"
                        f"❌ Sem EAN: {cat_stats.get('sem_ean', 0)}"
                    )

                    if cat_stats.get('por_tipo'):
                        principais_tipos = list(cat_stats['por_tipo'].items())[:3]
                        if principais_tipos:
                            cat_text += f"\n\n🏷️ Principais tipos:\n"
                            for tipo, count in principais_tipos:
                                cat_text += f"• {tipo}: {count}\n"

                    self.window.after(0, lambda: self.catalog_stats_var.set(cat_text))

                except Exception as e:
                    error_text = f"❌ Erro ao carregar:\n{str(e)[:50]}..."
                    self.window.after(0, lambda: self.catalog_stats_var.set(error_text))

                # Status dos bancos
                try:
                    products_exists = self.products_db_path.exists()
                    catalog_exists = self.catalog_db_path.exists()

                    products_size = self.products_db_path.stat().st_size if products_exists else 0
                    catalog_size = self.catalog_db_path.stat().st_size if catalog_exists else 0

                    status_text = (
                        f"🔧 Componentes: {'✅' if products_exists else '❌'} "
                        f"({self.format_file_size(products_size)})\n"
                        f"📋 Catálogo: {'✅' if catalog_exists else '❌'} "
                        f"({self.format_file_size(catalog_size)})\n"
                        f"📁 Pasta: {self.config.output_dir}"
                    )

                    self.window.after(0, lambda: self.db_status_var.set(status_text))

                except Exception as e:
                    error_text = f"❌ Erro ao verificar status:\n{str(e)[:50]}..."
                    self.window.after(0, lambda: self.db_status_var.set(error_text))

            except Exception as e:
                logger.error(f"Erro ao carregar dashboard: {e}")

        # Executar em thread separada
        thread = threading.Thread(target=load_data, daemon=True)
        thread.start()

    def format_file_size(self, size_bytes):
        """Formata tamanho do arquivo"""
        if size_bytes == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.1f} TB"

    def open_components_manager(self):
        """Abre gerenciador de componentes"""
        try:
            from .product_manager_window import ProductManagerWindow
            ProductManagerWindow(self.window, self.products_db_path)
        except Exception as e:
            logger.error(f"Erro ao abrir componentes: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir gerenciador:\n{e}")

    def open_catalog_manager(self):
        """Abre gerenciador de catálogo"""
        try:
            from .catalog_manager_window import CatalogManagerWindow
            CatalogManagerWindow(self.window, self.catalog_db_path)
        except Exception as e:
            logger.error(f"Erro ao abrir catálogo: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir catálogo:\n{e}")

    def import_components(self):
        """Importa componentes"""
        try:
            from .product_manager_window import ProductManagerWindow
            manager = ProductManagerWindow(self.window, self.products_db_path)
            # Simular clique no botão de importação
            manager.import_spreadsheet()
        except Exception as e:
            logger.error(f"Erro ao importar componentes: {e}")
            messagebox.showerror("Erro", f"Erro ao importar:\n{e}")

    def import_catalog(self):
        """Importa catálogo"""
        try:
            # Import local para evitar problemas de dependência circular
            from .catalog_import_dialog import CatalogImportDialog
            from ...core.product_catalog_database import ProductCatalogDatabase

            # ✅ CORREÇÃO: Verificar se catalog_db_path existe
            if not hasattr(self, 'catalog_db_path'):
                self.catalog_db_path = self.config.output_dir / "product_catalog.db"

            # Criar instância do banco
            catalog_db = ProductCatalogDatabase(self.catalog_db_path)

            # Abrir diálogo de importação
            dialog = CatalogImportDialog(self.window, catalog_db)
            self.window.wait_window(dialog.dialog)

            if dialog.result == "success":
                self.refresh_dashboard()

        except Exception as e:
            logger.error(f"Erro ao importar catálogo: {e}")
            messagebox.showerror("Erro", f"Erro ao importar:\n{e}")

    def refresh_dashboard(self):
        """Atualiza dashboard"""
        self.load_dashboard_data()

    def open_data_folder(self):
        """Abre pasta de dados"""
        try:
            import os
            import platform

            if platform.system() == "Windows":
                os.startfile(self.config.output_dir)
            elif platform.system() == "Darwin":  # macOS
                os.system(f"open '{self.config.output_dir}'")
            else:  # Linux
                os.system(f"xdg-open '{self.config.output_dir}'")

        except Exception as e:
            logger.error(f"Erro ao abrir pasta: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir pasta:\n{e}")

    def close_dashboard(self):
        """Fecha dashboard"""
        self.window.destroy()