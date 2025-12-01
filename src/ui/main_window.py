"""Interface gráfica principal com CustomTkinter"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import asyncio
import threading
import time  # ✅ ADICIONADO PARA OS LOGS
from pathlib import Path
from typing import Optional, List

from ..core.config import load_config, save_config
from ..core.models import EmailConfig
from ..processors.business_logic import ProductProcessor
from ..services.email_sender import EmailSender
from ..utils.logger import get_logger

# ✅ IMPORTS COM TRATAMENTO DE ERRO
try:
    from .components.progress_dialog import ProgressDialog
except ImportError:
    ProgressDialog = None

try:
    from .components.log_viewer import LogViewer
except ImportError:
    LogViewer = None

try:
    from .components.supplier_manager import SupplierManagerWindow
    from ..core.supplier_database import SupplierDatabase
    SUPPLIER_SYSTEM_AVAILABLE = True
except ImportError:
    SupplierManagerWindow = None
    SupplierDatabase = None
    SUPPLIER_SYSTEM_AVAILABLE = False

try:
    from .components.category_manager_window import CategoryManagerWindow
    from ..services.category_manager import CategoryManager
    CATEGORY_SYSTEM_AVAILABLE = True
except ImportError:
    CategoryManagerWindow = None
    CategoryManager = None
    CATEGORY_SYSTEM_AVAILABLE = False

logger = get_logger("main_window")

class MainWindow:
    """Janela principal da aplicação"""

    def __init__(self):
        # Configuração do tema
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ✅ CARREGA CONFIGURAÇÃO (UMA VEZ SÓ)
        self.config = load_config()

        # ✅ NOVO: Inicializar bancos embarcados ANTES de tudo
        self.initialize_embedded_databases()

        # ✅ CRIAR PROCESSOR (UMA VEZ SÓ)
        self.processor = ProductProcessor(self.config)

        # Inicializar banco de fornecedores
        if SUPPLIER_SYSTEM_AVAILABLE:
            try:
                self.supplier_db_path = self.config.output_dir / "suppliers.db"
                self.supplier_db = SupplierDatabase(self.supplier_db_path)
                self.initialize_supplier_database()
                logger.info(f"Banco de fornecedores inicializado: {self.supplier_db_path}")
            except Exception as e:
                logger.error(f"Erro ao inicializar banco de fornecedores: {e}")
                self.supplier_db = None
        else:
            logger.warning("Sistema de fornecedores não disponível")
            self.supplier_db = None

        # Inicializar gerenciador de categorias
        if CATEGORY_SYSTEM_AVAILABLE:
            try:
                self.category_manager = CategoryManager(
                    db_path=self.config.categories_db_path,
                    password=self.config.categories_password
                )
                logger.info(f"Gerenciador de categorias inicializado: {self.config.categories_db_path}")
            except Exception as e:
                logger.error(f"Erro ao inicializar gerenciador de categorias: {e}")
                self.category_manager = None
        else:
            logger.warning("Sistema de categorias não disponível")
            self.category_manager = None

        # Estado da aplicação
        self.processing = False
        self.progress_dialog = None
        self.processing_cancelled = False

        # Janelas secundárias
        self.catalog_window = None
        self.costs_window = None
        self.log_viewer = None

        # ✅ CONFIGURAR UI POR ÚLTIMO
        self.setup_ui()

    def initialize_supplier_database(self):
        """Inicializa banco com alguns fornecedores padrão"""
        if not self.supplier_db:
            return

        try:
            stats = self.supplier_db.get_statistics()  # ✅ MÉTODO CORRETO
            if stats["total_suppliers"] > 0:
                logger.info(f"Banco já possui {stats['total_suppliers']} fornecedores")
                return

            # ✅ ADICIONAR FORNECEDORES PADRÃO COM PRAZO
            default_suppliers = [
                ("DMOV", 51, 5),  # Nome, Código, Prazo em dias
            ]

            for name, code, prazo_dias in default_suppliers:
                self.supplier_db.add_supplier(name, code, prazo_dias)

            logger.info("Banco inicializado com fornecedores padrão")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco: {e}")

    def setup_ui(self):
        """Configura a interface"""
        self.root = ctk.CTk()
        self.root.title("📊 Cadastro Automático D'Rossi v2.1")
        self.root.minsize(800, 700)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Ícone
        try:
            if hasattr(self.config, 'logo_path') and self.config.logo_path and self.config.logo_path.exists():
                self.root.iconbitmap(str(self.config.logo_path))
        except Exception as e:
            logger.debug(f"Não foi possível carregar ícone: {e}")

        # Layout principal
        self.create_header()
        self.create_main_content()
        self.create_footer()

        self.root.after(100, self.maximize_window)

    def maximize_window(self):
        """Maximiza a janela após tudo estar carregado"""
        try:
            self.root.state('zoomed')
            self.root.after(200, lambda: self.root.state('zoomed'))
        except Exception as e:
            logger.debug(f"Erro ao maximizar: {e}")
            try:
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
                self.root.geometry(f"{screen_width - 10}x{screen_height - 50}+0+0")
            except Exception:
                self.root.geometry("1400x1000")

    def on_closing(self):
        """Callback quando a janela principal é fechada"""
        try:
            # ✅ FECHAR JANELAS FILHAS SEGURAMENTE
            for attr_name in ['log_viewer', 'catalog_window', 'costs_window', 'progress_dialog']:
                if hasattr(self, attr_name):
                    window = getattr(self, attr_name)
                    if window and hasattr(window, 'window') and window.window:
                        try:
                            if window.window.winfo_exists():
                                window.window.destroy()
                        except:
                            pass
                    elif window and hasattr(window, 'destroy'):
                        try:
                            window.destroy()
                        except:
                            pass

            if self.processing:
                if messagebox.askokcancel("Fechar", "Processamento em andamento. Deseja cancelar e fechar?"):
                    self.processing_cancelled = True
                    self.root.quit()
                    self.root.destroy()
                return

            self.root.quit()
            self.root.destroy()

        except Exception as e:
            logger.error(f"Erro ao fechar aplicação: {e}")
            # ✅ FORÇA SAÍDA EM CASO DE ERRO
            try:
                self.root.quit()
                self.root.destroy()
            except:
                import sys
                sys.exit(0)

    def create_header(self):
        """Cria o cabeçalho"""
        header_frame = ctk.CTkFrame(self.root, height=120)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(expand=True, fill="both")

        title_label = ctk.CTkLabel(
            title_frame,
            text="🏢 Sistema de Cadastro Automático",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        title_label.pack(pady=(20, 5))

        subtitle_label = ctk.CTkLabel(
            title_frame,
            text="Processamento inteligente de planilhas de produtos D'Rossi",
            font=ctk.CTkFont(size=16),
            text_color=("gray60", "gray40")
        )
        subtitle_label.pack(pady=(0, 20))

    def create_main_content(self):
        """Cria o conteúdo principal"""
        self.main_frame = ctk.CTkScrollableFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.create_file_section()
        self.create_config_section()
        self.create_pricing_section()
        self.create_email_section()
        self.create_processing_section()

    def create_file_section(self):
        """Seção de seleção de arquivos"""
        files_frame = ctk.CTkFrame(self.main_frame)
        files_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            files_frame,
            text="📁 Seleção de Arquivos",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        self.create_file_input(
            files_frame,
            "Planilha de Origem *",
            "Selecione a planilha Excel com os dados dos produtos...",
            "origin_file"
        )

        # ✅ ADICIONAR INFO SOBRE CATEGORIAS
        info_frame = ctk.CTkFrame(files_frame, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=(10, 20))

        ctk.CTkLabel(
            info_frame,
            text="ℹ️ Categorias:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        ctk.CTkLabel(
            info_frame,
            text="As categorias são gerenciadas pelo banco de dados interno (DB_CATEGORIAS.json)",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame,
            text="Use o botão '🏷️ Categorias' para gerenciar as categorias da loja web",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        ).pack(anchor="w", pady=(2, 0))

    def create_file_input(self, parent, label_text, placeholder, var_name):
        """Cria um input de arquivo reutilizável"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="x", padx=20, pady=10)

        label = ctk.CTkLabel(
            container,
            text=label_text,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        label.pack(anchor="w", pady=(0, 5))

        input_frame = ctk.CTkFrame(container)
        input_frame.pack(fill="x", pady=(0, 5))

        var = tk.StringVar()
        setattr(self, f"{var_name}_var", var)

        entry = ctk.CTkEntry(
            input_frame,
            textvariable=var,
            placeholder_text=placeholder
        )
        entry.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=15)

        button = ctk.CTkButton(
            input_frame,
            text="📂 Procurar",
            command=lambda: self.select_file(var, f"Selecionar {label_text}"),
            width=120
        )
        button.pack(side="right", padx=(0, 15), pady=15)

    def create_config_section(self):
        """Seção de configurações"""
        config_frame = ctk.CTkFrame(self.main_frame)
        config_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            config_frame,
            text="⚙️ Configurações",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        config_grid = ctk.CTkFrame(config_frame, fg_color="transparent")
        config_grid.pack(fill="x", padx=20, pady=(0, 20))
        config_grid.grid_columnconfigure(1, weight=1)

        # Marca padrão
        ctk.CTkLabel(
            config_grid,
            text="Marca Padrão:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 20), pady=10)

        self.brand_var = tk.StringVar(value=self.config.default_brand)
        brand_entry = ctk.CTkEntry(
            config_grid,
            textvariable=self.brand_var,
            placeholder_text="Ex: Dmov"
        )
        brand_entry.grid(row=0, column=1, sticky="ew", pady=10)

        # ✅ NOVA SEÇÃO: Aba de origem com dropdown automático
        ctk.CTkLabel(
            config_grid,
            text="Aba de Origem:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=1, column=0, sticky="w", padx=(0, 20), pady=10)

        # ✅ FRAME PARA DROPDOWN + BOTÃO REFRESH
        sheet_selector_frame = ctk.CTkFrame(config_grid, fg_color="transparent")
        sheet_selector_frame.grid(row=1, column=1, sticky="ew", pady=10)
        sheet_selector_frame.grid_columnconfigure(0, weight=1)

        # ✅ DROPDOWN DAS ABAS
        self.sheet_combobox = ctk.CTkComboBox(
            sheet_selector_frame,
            values=["Selecione um arquivo primeiro..."],
            state="readonly",
            width=300
        )
        self.sheet_combobox.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.sheet_combobox.set("Selecione um arquivo primeiro...")

        # ✅ BOTÃO PARA ATUALIZAR LISTA DE ABAS
        self.refresh_sheets_btn = ctk.CTkButton(
            sheet_selector_frame,
            text="🔄",
            width=40,
            command=self.refresh_sheet_list
        )
        self.refresh_sheets_btn.grid(row=0, column=1)

        # ✅ LABEL DE STATUS DAS ABAS
        self.sheet_status_label = ctk.CTkLabel(
            config_grid,
            text="📋 Selecione um arquivo primeiro para ver as abas disponíveis",
            font=ctk.CTkFont(size=11),
            text_color=("gray60", "gray40")
        )
        self.sheet_status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # Informação sobre fornecedores
        info_frame = ctk.CTkFrame(config_grid, fg_color="transparent")
        info_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(15, 0))

        ctk.CTkLabel(
            info_frame,
            text="ℹ️ O código do fornecedor será buscado automaticamente no banco de dados baseado na marca informada",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40"),
            wraplength=600
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame,
            text="🗄️ Use o botão 'Fornecedores' para gerenciar o banco de dados",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40"),
            wraplength=600
        ).pack(anchor="w", pady=(5, 0))

    def create_pricing_section(self):
        """Seção de configuração de precificação automática"""
        pricing_frame = ctk.CTkFrame(self.main_frame)
        pricing_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            pricing_frame,
            text="💰 Precificação Automática",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        self.enable_pricing_var = tk.BooleanVar(value=False)
        self.enable_pricing_checkbox = ctk.CTkCheckBox(
            pricing_frame,
            text="🏷️ Habilitar Precificação Automática",
            variable=self.enable_pricing_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_pricing_fields
        )
        self.enable_pricing_checkbox.pack(padx=20, pady=(0, 15))

        self.pricing_fields_frame = ctk.CTkFrame(pricing_frame, fg_color="transparent")
        self.pricing_fields_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Arquivo de custos
        cost_file_container = ctk.CTkFrame(self.pricing_fields_frame, fg_color="transparent")
        cost_file_container.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            cost_file_container,
            text="Planilha de Custos:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        cost_file_input_frame = ctk.CTkFrame(cost_file_container)
        cost_file_input_frame.pack(fill="x", pady=(0, 5))

        self.cost_file_var = tk.StringVar()
        self.cost_file_entry = ctk.CTkEntry(
            cost_file_input_frame,
            textvariable=self.cost_file_var,
            placeholder_text="Selecione a planilha de custos..."
        )
        self.cost_file_entry.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=15)

        self.cost_file_button = ctk.CTkButton(
            cost_file_input_frame,
            text="📂 Procurar",
            command=lambda: self.select_file(self.cost_file_var, "Selecionar Planilha de Custos"),
            width=120
        )
        self.cost_file_button.pack(side="right", padx=(0, 15), pady=15)

        # Configurações de precificação
        pricing_config_grid = ctk.CTkFrame(self.pricing_fields_frame, fg_color="transparent")
        pricing_config_grid.pack(fill="x", pady=(10, 0))
        pricing_config_grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            pricing_config_grid,
            text="Modo de Precificação:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 20), pady=10)

        self.pricing_mode_var = tk.StringVar(value="Fábrica")
        self.pricing_mode_combo = ctk.CTkComboBox(
            pricing_config_grid,
            variable=self.pricing_mode_var,
            values=["Fábrica", "Fornecedor"],
            state="readonly"
        )
        self.pricing_mode_combo.grid(row=0, column=1, sticky="ew", pady=10)

        # Opções de precificação
        pricing_options_frame = ctk.CTkFrame(self.pricing_fields_frame, fg_color="transparent")
        pricing_options_frame.pack(fill="x", pady=(15, 0))

        self.apply_90_cents_var = tk.BooleanVar(value=False)
        self.apply_90_cents_checkbox = ctk.CTkCheckBox(
            pricing_options_frame,
            text="💰 Aplicar regra dos 90 centavos nos preços",
            variable=self.apply_90_cents_var,
            font=ctk.CTkFont(size=13)
        )
        self.apply_90_cents_checkbox.pack(anchor="w", pady=(0, 10))

        # Info sobre precificação
        info_frame = ctk.CTkFrame(self.pricing_fields_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkLabel(
            info_frame,
            text="ℹ️ A precificação automática preencherá: VR Custo Total, Custo IPI, Custo Frete, Preço de Venda e Preço Promoção",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40"),
            wraplength=700
        ).pack(anchor="w", pady=(0, 5))

        self.toggle_pricing_fields()

    def toggle_pricing_fields(self):
        """Ativa/desativa campos de precificação"""
        state = "normal" if self.enable_pricing_var.get() else "disabled"

        pricing_widgets = [
            self.cost_file_entry,
            self.cost_file_button,
            self.pricing_mode_combo,
            self.apply_90_cents_checkbox
        ]

        for widget in pricing_widgets:
            widget.configure(state=state)

    def create_email_section(self):
        """Seção de configuração de e-mail"""
        email_frame = ctk.CTkFrame(self.main_frame)
        email_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            email_frame,
            text="📧 Configuração de E-mail",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        self.send_email_var = tk.BooleanVar(value=True)
        self.send_email_checkbox = ctk.CTkCheckBox(
            email_frame,
            text="📧 Enviar relatório por e-mail após processamento",
            variable=self.send_email_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_email_fields
        )
        self.send_email_checkbox.pack(padx=20, pady=(0, 15))

        self.email_fields_frame = ctk.CTkFrame(email_frame, fg_color="transparent")
        self.email_fields_frame.pack(fill="x", padx=20, pady=(0, 20))

        email_grid = ctk.CTkFrame(self.email_fields_frame, fg_color="transparent")
        email_grid.pack(fill="x")
        email_grid.grid_columnconfigure(1, weight=1)

        # Valores padrão
        email_username = "cadastroautomaticodrossi@gmail.com"
        email_password = "lygl jwsj wjhx cwuf"
        email_recipients = "cadastro6@drossiinteriores.com.br"

        if self.config.email:
            email_username = self.config.email.username
            email_password = self.config.email.password
            email_recipients = ", ".join(self.config.email.to_addrs)

        # E-mail
        ctk.CTkLabel(
            email_grid,
            text="E-mail (Gmail):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 20), pady=10)

        self.email_username_var = tk.StringVar(value=email_username)
        self.email_username_entry = ctk.CTkEntry(
            email_grid,
            textvariable=self.email_username_var,
            placeholder_text="seu.email@gmail.com"
        )
        self.email_username_entry.grid(row=0, column=1, sticky="ew", pady=10)

        # Senha
        ctk.CTkLabel(
            email_grid,
            text="Senha do App:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=1, column=0, sticky="w", padx=(0, 20), pady=10)

        self.email_password_var = tk.StringVar(value=email_password)
        self.email_password_entry = ctk.CTkEntry(
            email_grid,
            textvariable=self.email_password_var,
            placeholder_text="Senha de app do Gmail",
            show="*"
        )
        self.email_password_entry.grid(row=1, column=1, sticky="ew", pady=10)

        # Destinatários
        ctk.CTkLabel(
            email_grid,
            text="Destinatários:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=2, column=0, sticky="w", padx=(0, 20), pady=10)

        self.email_recipients_var = tk.StringVar(value=email_recipients)
        self.email_recipients_entry = ctk.CTkEntry(
            email_grid,
            textvariable=self.email_recipients_var,
            placeholder_text="email1@exemplo.com, email2@exemplo.com"
        )
        self.email_recipients_entry.grid(row=2, column=1, sticky="ew", pady=10)

        # Botões
        email_buttons_frame = ctk.CTkFrame(self.email_fields_frame, fg_color="transparent")
        email_buttons_frame.pack(fill="x", pady=(15, 0))

        self.test_email_btn = ctk.CTkButton(
            email_buttons_frame,
            text="🧪 Testar Conexão",
            command=self.test_email_connection,
            width=150,
            height=35
        )
        self.test_email_btn.pack(side="left", padx=(0, 10))

        self.save_config_btn = ctk.CTkButton(
            email_buttons_frame,
            text="💾 Salvar Configurações",
            command=self.save_email_config,
            width=180,
            height=35
        )
        self.save_config_btn.pack(side="left")

        self.toggle_email_fields()

    def toggle_email_fields(self):
        """Ativa/desativa campos de e-mail"""
        state = "normal" if self.send_email_var.get() else "disabled"

        email_widgets = [
            self.email_username_entry,
            self.email_password_entry,
            self.email_recipients_entry,
            self.test_email_btn,
            self.save_config_btn
        ]

        for widget in email_widgets:
            widget.configure(state=state)

    def create_processing_section(self):
        """Seção de processamento"""
        process_frame = ctk.CTkFrame(self.main_frame)
        process_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            process_frame,
            text="🚀 Processamento",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        # Botões
        button_frame = ctk.CTkFrame(process_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 15))

        # Botão principal
        self.process_button = ctk.CTkButton(
            button_frame,
            text="▶️ Processar Planilha",
            command=self.start_processing,
            font=ctk.CTkFont(size=18, weight="bold"),
            height=60,
            corner_radius=10
        )
        self.process_button.pack(side="left", padx=(0, 15))

        # Botões secundários
        secondary_frame = ctk.CTkFrame(button_frame, fg_color="transparent")
        secondary_frame.pack(side="left", fill="x", expand=True)

        # Primeira linha de botões
        first_row = ctk.CTkFrame(secondary_frame, fg_color="transparent")
        first_row.pack(fill="x", pady=(0, 5))

        ctk.CTkButton(
            first_row,
            text="📋 Ver Logs",
            command=self.show_logs,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            first_row,
            text="📁 Abrir Pasta Saída",
            command=self.open_output_folder,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            first_row,
            text="🗄️ Fornecedores",
            command=self.show_supplier_manager,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            first_row,
            text="🏷️ Categorias",
            command=self.show_category_manager,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        # Segunda linha de botões
        second_row = ctk.CTkFrame(secondary_frame, fg_color="transparent")
        second_row.pack(fill="x")

        ctk.CTkButton(
            second_row,
            text="🛋️ Componentes",
            command=self.show_product_manager,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            second_row,
            text="📋 Catálogo",
            command=self.show_catalog_manager,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        # ✅ BOTÃO CUSTOS CORRIGIDO
        ctk.CTkButton(
            second_row,
            text="💰 Custos",
            command=self.show_costs_manager,
            height=40,
            width=130
        ).pack(side="left", padx=(0, 10))

        # Status
        status_frame = ctk.CTkFrame(process_frame, fg_color="transparent")
        status_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.status_var = tk.StringVar(value="Pronto para processar")
        self.status_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        self.status_label.pack(fill="x", pady=(10, 5))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(
            status_frame,
            variable=self.progress_var,
            height=20
        )
        self.progress_bar.pack(fill="x", pady=(5, 10))
        self.progress_bar.pack_forget()

    def create_footer(self):
        """Cria o rodapé"""
        footer_frame = ctk.CTkFrame(self.root, height=60)
        footer_frame.pack(fill="x", padx=20, pady=(10, 20))
        footer_frame.pack_propagate(False)

        footer_content = ctk.CTkFrame(footer_frame, fg_color="transparent")
        footer_content.pack(expand=True, fill="both")

        ctk.CTkLabel(
            footer_content,
            text="© 2025 D'Rossi Interiores - Sistema de Cadastro Automático v2.1",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        ).pack(expand=True)

    # ✅ MÉTODOS CORRIGIDOS COM INDENTAÇÃO ADEQUADA

    def select_file(self, var: tk.StringVar, title: str):
        """Seleciona arquivo"""
        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            var.set(file_path)

            # ✅ AUTO-ATUALIZAR ABAS SE FOR ARQUIVO DE ORIGEM
            if var == self.origin_file_var:
                # ✅ USAR TIMER PARA EVITAR TRAVAMENTO DA UI
                self.root.after(100, self.on_file_selected)

    def refresh_sheet_list(self):
        """Atualiza lista de abas disponíveis"""
        try:
            if not hasattr(self, 'origin_file_var') or not self.origin_file_var.get():
                messagebox.showwarning("⚠️ Aviso", "Selecione um arquivo primeiro!")
                return

            origin_file_path = Path(self.origin_file_var.get())
            if not origin_file_path.exists():
                messagebox.showerror("❌ Erro", "Arquivo selecionado não existe!")
                return

            # ✅ USAR EXCEL_READER PARA OBTER ABAS
            from ..processors.excel_reader import ExcelReader
            reader = ExcelReader()

            logger.info(f"🔍 Buscando abas do arquivo: {origin_file_path}")
            sheet_names = reader.get_sheet_names(origin_file_path)

            if sheet_names:
                # ✅ ATUALIZAR DROPDOWN
                self.sheet_combobox.configure(values=sheet_names)

                # ✅ AUTO-SELECIONAR ABA MAIS PROVÁVEL
                default_sheet = self.guess_default_sheet(sheet_names)
                if default_sheet:
                    self.sheet_combobox.set(default_sheet)
                    self.sheet_status_label.configure(
                        text=f"✅ {len(sheet_names)} abas encontradas. Selecionada: '{default_sheet}'"
                    )
                    logger.success(f"✅ Aba padrão selecionada: '{default_sheet}'")
                else:
                    self.sheet_combobox.set(sheet_names[0])
                    self.sheet_status_label.configure(
                        text=f"✅ {len(sheet_names)} abas encontradas. Primeira aba selecionada."
                    )

                logger.success(f"✅ Lista de abas atualizada: {sheet_names}")

            else:
                self.sheet_combobox.configure(values=["Nenhuma aba encontrada"])
                self.sheet_combobox.set("Nenhuma aba encontrada")
                self.sheet_status_label.configure(
                    text="❌ Não foi possível ler as abas do arquivo"
                )
                logger.error("❌ Nenhuma aba encontrada no arquivo")

        except Exception as e:
            logger.error(f"Erro ao atualizar lista de abas: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao ler abas do arquivo:\n{e}")

    def guess_default_sheet(self, sheet_names: List[str]) -> Optional[str]:
        """Tenta adivinhar qual é a aba principal baseado no nome"""
        # ✅ PRIORIDADES DE NOMES COMUNS
        priority_names = [
            "Produtos", "produtos", "PRODUTOS",
            "Planilha", "planilha", "PLANILHA",
            "Dados", "dados", "DADOS",
            "Sheet1", "Plan1", "Aba1",
            "Produto", "produto", "PRODUTO"
        ]

        # ✅ BUSCA EXATA PRIMEIRO
        for priority in priority_names:
            if priority in sheet_names:
                logger.info(f"🎯 Aba padrão encontrada (exata): '{priority}'")
                return priority

        # ✅ BUSCA PARCIAL (CONTÉM)
        for priority in priority_names:
            for sheet in sheet_names:
                if priority.lower() in sheet.lower():
                    logger.info(f"🎯 Aba padrão encontrada (parcial): '{sheet}' (contém '{priority}')")
                    return sheet

        # ✅ SE NÃO ENCONTROU, RETORNA A PRIMEIRA
        if sheet_names:
            logger.info(f"🎯 Usando primeira aba como padrão: '{sheet_names[0]}'")
            return sheet_names[0]

        return None

    def on_file_selected(self):
        """Callback quando arquivo é selecionado - auto-atualizar abas"""
        try:
            if hasattr(self, 'origin_file_var') and self.origin_file_var.get():
                # ✅ AUTO-ATUALIZAR LISTA DE ABAS
                self.refresh_sheet_list()
        except Exception as e:
            logger.error(f"Erro ao auto-atualizar abas: {e}")

    def test_email_connection(self):
        """Testa conexão de e-mail"""
        try:
            if not self.email_username_var.get():
                messagebox.showerror("Erro", "Digite o e-mail")
                return

            if not self.email_password_var.get():
                messagebox.showerror("Erro", "Digite a senha do app")
                return

            email_config = EmailConfig(
                username=self.email_username_var.get(),
                password=self.email_password_var.get(),
                from_addr=self.email_username_var.get(),
                to_addrs=[addr.strip() for addr in self.email_recipients_var.get().split(',') if addr.strip()]
            )

            def test_connection():
                try:
                    sender = EmailSender(email_config)
                    success = sender.test_connection()

                    if success:
                        self.root.after(0, lambda: messagebox.showinfo(
                            "Sucesso",
                            "✅ Conexão testada com sucesso!\nO e-mail está configurado corretamente."
                        ))
                    else:
                        self.root.after(0, lambda: messagebox.showerror(
                            "Erro",
                            "❌ Erro na conexão.\nVerifique as configurações de e-mail."
                        ))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Erro",
                        f"❌ Erro ao testar conexão:\n{str(e)}"
                    ))

            self.test_email_btn.configure(state="disabled", text="🔄 Testando...")

            thread = threading.Thread(target=test_connection, daemon=True)
            thread.start()

            self.root.after(5000, lambda: self.test_email_btn.configure(
                state="normal", text="🧪 Testar Conexão"
            ))

        except Exception as e:
            messagebox.showerror("Erro", f"❌ Erro: {e}")

    def save_email_config(self):
        """Salva configurações de e-mail"""
        try:
            if self.email_username_var.get() and self.email_password_var.get():
                self.config.email = EmailConfig(
                    username=self.email_username_var.get(),
                    password=self.email_password_var.get(),
                    from_addr=self.email_username_var.get(),
                    to_addrs=[addr.strip() for addr in self.email_recipients_var.get().split(',') if addr.strip()]
                )
            else:
                self.config.email = None

            self.config.default_brand = self.brand_var.get() or "D'Rossi"
            save_config(self.config)

            messagebox.showinfo("Sucesso", "✅ Configurações salvas com sucesso!")

        except Exception as e:
            messagebox.showerror("Erro", f"❌ Erro ao salvar configurações:\n{e}")

    def start_processing(self):
        """Inicia o processamento"""
        if not self.origin_file_var.get():
            messagebox.showerror("Erro", "Selecione a planilha de origem")
            return

        if self.processing:
            messagebox.showwarning("Aviso", "Processamento já em andamento")
            return

        if self.enable_pricing_var.get():
            if not self.cost_file_var.get():
                messagebox.showerror("Erro", "Selecione a planilha de custos ou desabilite a precificação automática")
                return

            cost_file_path = Path(self.cost_file_var.get())
            if not cost_file_path.exists():
                messagebox.showerror("Erro", f"Arquivo de custos não encontrado:\n{cost_file_path}")
                return

        if self.send_email_var.get():
            if not self.email_username_var.get() or not self.email_password_var.get():
                messagebox.showerror(
                    "Erro",
                    "Configure o e-mail ou desative o envio de relatório"
                )
                return

        # ✅ ABRIR LOGS AUTOMATICAMENTE
        self.show_logs()

        self.processing = True
        self.processing_cancelled = False
        thread = threading.Thread(target=self.run_processing, daemon=True)
        thread.start()

    def run_processing(self):
        """Executa processamento em thread separada"""
        try:
            origin_file = Path(self.origin_file_var.get())

            # ✅ USAR ABA SELECIONADA NO DROPDOWN
            selected_sheet = self.sheet_combobox.get()
            if not selected_sheet or selected_sheet in [
                "Selecione um arquivo primeiro...",
                "Nenhuma aba encontrada",
                "Selecione uma aba..."
            ]:
                self.root.after(0, lambda: messagebox.showerror("❌ Erro", "Selecione uma aba válida!"))
                return

            sheet_name = selected_sheet
            logger.info(f"📋 Aba selecionada para processamento: '{sheet_name}'")

            # Configuração da marca e fornecedor
            brand_name = self.brand_var.get() or "D'Rossi"
            self.config.default_brand = brand_name

            supplier_code, official_brand_name = self.resolve_supplier_code(brand_name)
            self.config.supplier_code = supplier_code
            self.config.default_brand = official_brand_name

            logger.info(f"Configuração de fornecedor:")
            logger.info(f"  - Nome informado: '{brand_name}'")
            logger.info(f"  - Nome oficial (banco): '{official_brand_name}'")
            logger.info(f"  - Código encontrado: {supplier_code}")

            # Configuração de precificação
            if self.enable_pricing_var.get():
                self.config.enable_auto_pricing = True

                if self.cost_file_var.get() and self.cost_file_var.get().strip():
                    self.config.cost_file_path = Path(self.cost_file_var.get())
                else:
                    self.root.after(0, lambda: messagebox.showerror("Erro",
                                                                    "Selecione a planilha de custos para habilitar a precificação automática"))
                    return

                from ..core.models import PricingMode
                if self.pricing_mode_var.get() == "Fábrica":
                    self.config.pricing_mode = PricingMode.FABRICA
                else:
                    self.config.pricing_mode = PricingMode.FORNECEDOR

                self.config.apply_90_cents_rule = self.apply_90_cents_var.get()

                logger.info(f"Precificação automática habilitada:")
                logger.info(f"  - Arquivo de custos: {self.config.cost_file_path}")
                logger.info(f"  - Modo: {self.config.pricing_mode.value}")
                logger.info(f"  - Regra 90 centavos: {self.config.apply_90_cents_rule}")
            else:
                self.config.enable_auto_pricing = False
                self.config.cost_file_path = None
                logger.info("Precificação automática desabilitada")

            # Configuração de e-mail
            if self.send_email_var.get() and self.email_username_var.get():
                self.config.email = EmailConfig(
                    username=self.email_username_var.get(),
                    password=self.email_password_var.get(),
                    from_addr=self.email_username_var.get(),
                    to_addrs=[addr.strip() for addr in self.email_recipients_var.get().split(',') if addr.strip()]
                )
                # ✅ RECRIAR PROCESSOR COM NOVA CONFIGURAÇÃO
                self.processor = ProductProcessor(self.config)

            self.root.after(0, self.show_progress_dialog)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            result = loop.run_until_complete(
                self.processor.process_products(
                    origin_file=origin_file,
                    sheet_name=sheet_name,
                    progress_callback=self.update_progress,
                    status_callback=self.update_status,
                    send_email=self.send_email_var.get()
                )
            )

            if self.processing_cancelled:
                logger.info("Processamento cancelado pelo usuário")
                return

            self.root.after(0, lambda: self.show_result(result))

        except Exception as e:
            error_msg = str(e)  # ✅ CAPTURAR ERRO EM VARIÁVEL LOCAL
            logger.error(f"Erro no processamento: {error_msg}")

            if not self.processing_cancelled:
                # ✅ USAR VARIÁVEL LOCAL PARA EVITAR ERRO DE ESCOPO
                self.root.after(0, lambda msg=error_msg: messagebox.showerror("Erro", f"Erro no processamento:\n{msg}"))
        finally:
            self.processing = False
            self.root.after(0, self.hide_progress_dialog)

    def show_progress_dialog(self):
        """Mostra diálogo de progresso"""
        try:
            self.progress_dialog = ProgressDialog(self.root)
            self.progress_bar.pack(fill="x", pady=(5, 10))
            self.process_button.configure(state="disabled", text="🔄 Processando...")
        except Exception as e:
            logger.error(f"Erro ao criar diálogo de progresso: {e}")
            self.progress_bar.pack(fill="x", pady=(5, 10))
            self.process_button.configure(state="disabled", text="🔄 Processando...")

    def hide_progress_dialog(self):
        """Oculta diálogo de progresso"""
        try:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                try:
                    if hasattr(self.progress_dialog, 'winfo_exists') and self.progress_dialog.winfo_exists():
                        self.progress_dialog.destroy()
                except:
                    pass
                finally:
                    self.progress_dialog = None
        except Exception as e:
            logger.debug(f"Erro ao fechar diálogo: {e}")
            self.progress_dialog = None

        # ✅ PROTEGER ATUALIZAÇÕES DE UI
        try:
            self.progress_bar.pack_forget()
            self.process_button.configure(state="normal", text="▶️ Processar Planilha")
            self.progress_var.set(0)
            self.status_var.set("Pronto para processar")
        except Exception as e:
            logger.debug(f"Erro ao atualizar UI: {e}")

    def update_progress(self, value: float):
        """Atualiza progresso"""
        try:
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(0, lambda: self.progress_var.set(value))
                if self.progress_dialog and hasattr(self.progress_dialog, 'update_progress'):
                    self.root.after(0, lambda: self.progress_dialog.update_progress(value))
        except Exception as e:
            logger.debug(f"Erro ao atualizar progresso: {e}")

    def update_status(self, message: str):
        """Atualiza status"""
        try:
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(0, lambda: self.status_var.set(message))
                if self.progress_dialog and hasattr(self.progress_dialog, 'update_status'):
                    self.root.after(0, lambda: self.progress_dialog.update_status(message))
        except Exception as e:
            logger.debug(f"Erro ao atualizar status: {e}")


    def show_result(self, result):
        """Mostra resultado do processamento"""
        if result.success:
            email_status = ""
            if self.send_email_var.get():
                if result.warnings and any("E-mail" in w for w in result.warnings):
                    email_status = "\n⚠️ Arquivo processado, mas e-mail não foi enviado"
                else:
                    email_status = "\n📧 Relatório enviado por e-mail"

            message = (
                f"✅ Processamento concluído com sucesso!{email_status}\n\n"
                f"📊 Produtos processados: {result.total_products}\n"
                f"🔄 Variações criadas: {result.total_variations}\n"
                f"📦 Kits processados: {result.total_kits}\n"
                f"⚠️ Erros encontrados: {result.total_errors}\n"
                f"⏱️ Tempo total: {result.processing_time:.2f}s\n"
                f"📈 Taxa de sucesso: {result.success_rate*100:.1f}%\n\n"
                f"📁 Arquivo salvo em:\n{result.output_file}"
            )
            messagebox.showinfo("Sucesso!", message)
        else:
            error_msg = "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                error_msg += f"\n... e mais {len(result.errors)-5} erros"

            messagebox.showerror(
                "Erro no Processamento",
                f"❌ Falha no processamento:\n\n{error_msg}"
            )

    def show_logs(self):
        """Mostra logs simples sem tempo real"""
        try:
            # ✅ VERSÃO SIMPLES: Apenas mostra logs existentes
            import os
            from pathlib import Path

            # Buscar arquivo de log
            log_files = []
            possible_log_paths = [
                Path("logs") / "app.log",
                Path("outputs") / "app.log",
                Path("app.log"),
                Path("cadastro_automatico.log")
            ]

            for log_path in possible_log_paths:
                if log_path.exists():
                    log_files.append(log_path)

            if not log_files:
                messagebox.showinfo("📋 Logs",
                                    "Nenhum arquivo de log encontrado ainda.\n\nOs logs aparecerão após o primeiro processamento.")
                return

            # Usar o arquivo de log mais recente
            log_file = max(log_files, key=lambda f: f.stat().st_mtime)

            # ✅ JANELA SIMPLES PARA MOSTRAR LOGS
            log_window = ctk.CTkToplevel(self.root)
            log_window.title("📋 Logs do Sistema")
            log_window.geometry("900x700")

            # ✅ HEADER COM INFORMAÇÕES
            header_frame = ctk.CTkFrame(log_window)
            header_frame.pack(fill="x", padx=10, pady=(10, 5))

            ctk.CTkLabel(
                header_frame,
                text=f"📁 Arquivo: {log_file.name}",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(side="left", padx=10, pady=10)

            # ✅ BOTÕES DE CONTROLE
            buttons_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
            buttons_frame.pack(side="right", padx=10, pady=5)

            refresh_btn = ctk.CTkButton(
                buttons_frame,
                text="🔄 Atualizar",
                command=lambda: self.refresh_simple_logs(text_area, log_file, status_label),
                width=100,
                height=30
            )
            refresh_btn.pack(side="left", padx=5)

            clear_btn = ctk.CTkButton(
                buttons_frame,
                text="🗑️ Limpar",
                command=lambda: self.clear_simple_logs(text_area, status_label),
                width=100,
                height=30
            )
            clear_btn.pack(side="left", padx=5)

            open_folder_btn = ctk.CTkButton(
                buttons_frame,
                text="📁 Abrir Pasta",
                command=lambda: self.open_log_folder(log_file),
                width=120,
                height=30
            )
            open_folder_btn.pack(side="left", padx=5)

            # ✅ STATUS
            status_frame = ctk.CTkFrame(log_window)
            status_frame.pack(fill="x", padx=10, pady=5)

            status_label = ctk.CTkLabel(
                status_frame,
                text="📊 Carregando logs...",
                font=ctk.CTkFont(size=12)
            )
            status_label.pack(side="left", padx=10, pady=5)

            # ✅ ÁREA DE TEXTO SIMPLES
            text_frame = ctk.CTkFrame(log_window)
            text_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

            # Criar Text widget com scrollbar
            text_area = tk.Text(
                text_frame,
                wrap=tk.WORD,
                font=("Consolas", 10),
                bg="#1a1a1a",
                fg="#ffffff",
                insertbackground="#ffffff",
                selectbackground="#404040",
                state='disabled'  # ✅ SOMENTE LEITURA
            )

            scrollbar = tk.Scrollbar(text_frame, command=text_area.yview)
            text_area.config(yscrollcommand=scrollbar.set)

            text_area.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
            scrollbar.pack(side="right", fill="y", pady=10, padx=(0, 10))

            # ✅ CONFIGURAR CORES PARA DIFERENTES NÍVEIS
            text_area.tag_config("INFO", foreground="#00ff00")
            text_area.tag_config("SUCCESS", foreground="#00ff00", font=("Consolas", 10, "bold"))
            text_area.tag_config("WARNING", foreground="#ffff00")
            text_area.tag_config("ERROR", foreground="#ff0000")
            text_area.tag_config("DEBUG", foreground="#888888")
            text_area.tag_config("CRITICAL", foreground="#ff0000", font=("Consolas", 10, "bold"))

            # ✅ CARREGAR LOGS INICIALMENTE
            self.load_simple_logs(text_area, log_file, status_label)

        except Exception as e:
            logger.error(f"Erro ao abrir logs: {e}")
            messagebox.showerror("❌ Erro", f"Não foi possível abrir os logs:\n{e}")

    def load_simple_logs(self, text_area, log_file, status_label):
        """Carrega logs do arquivo"""
        try:
            # Ler arquivo de log
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()

            if not log_content.strip():
                log_content = "📝 Arquivo de log vazio.\n\nOs logs aparecerão após executar algum processamento."

            # ✅ HABILITAR EDIÇÃO TEMPORARIAMENTE
            text_area.config(state='normal')
            text_area.delete('1.0', tk.END)

            # ✅ INSERIR CONTEÚDO COM CORES
            lines = log_content.split('\n')
            for line in lines:
                if not line.strip():
                    text_area.insert(tk.END, '\n')
                    continue

                # ✅ DETECTAR NÍVEL DO LOG E APLICAR COR
                if 'ERROR' in line or 'CRITICAL' in line:
                    text_area.insert(tk.END, line + '\n', 'ERROR')
                elif 'WARNING' in line:
                    text_area.insert(tk.END, line + '\n', 'WARNING')
                elif 'SUCCESS' in line or '✅' in line:
                    text_area.insert(tk.END, line + '\n', 'SUCCESS')
                elif 'DEBUG' in line:
                    text_area.insert(tk.END, line + '\n', 'DEBUG')
                else:
                    text_area.insert(tk.END, line + '\n', 'INFO')

            # ✅ VOLTAR PARA SOMENTE LEITURA
            text_area.config(state='disabled')

            # ✅ SCROLL PARA O FINAL
            text_area.see(tk.END)

            # ✅ ATUALIZAR STATUS (CORRIGIDO)
            file_size = log_file.stat().st_size
            line_count = len(lines)
            last_modified = time.ctime(log_file.stat().st_mtime)  # ✅ AGORA FUNCIONA
            status_label.configure(
                text=f"📊 {line_count} linhas • {file_size} bytes • Última modificação: {last_modified}"
            )

        except Exception as e:
            text_area.config(state='normal')
            text_area.delete('1.0', tk.END)
            text_area.insert('1.0', f"❌ Erro ao ler arquivo de log:\n{e}")
            text_area.config(state='disabled')
            status_label.configure(text="❌ Erro ao carregar logs")

    def refresh_simple_logs(self, text_area, log_file, status_label):
        """Atualiza logs sem travamento"""
        try:
            status_label.configure(text="🔄 Atualizando...")

            # ✅ USAR AFTER PARA NÃO TRAVAR A UI
            self.root.after(100, lambda: self.load_simple_logs(text_area, log_file, status_label))

        except Exception as e:
            messagebox.showerror("❌ Erro", f"Erro ao atualizar logs:\n{e}")

    def clear_simple_logs(self, text_area, status_label):
        """Limpa visualização dos logs"""
        try:
            result = messagebox.askyesno(
                "🗑️ Limpar Logs",
                "Deseja limpar a visualização dos logs?\n\n(O arquivo original não será alterado)"
            )

            if result:
                text_area.config(state='normal')
                text_area.delete('1.0', tk.END)
                text_area.insert('1.0', "📝 Logs limpos.\n\nClique em 'Atualizar' para recarregar do arquivo.")
                text_area.config(state='disabled')
                status_label.configure(text="🗑️ Visualização limpa")

        except Exception as e:
            messagebox.showerror("❌ Erro", f"Erro ao limpar logs:\n{e}")

    def open_log_folder(self, log_file):
        """Abre pasta dos logs"""
        try:
            import os
            import subprocess
            import platform

            log_folder = log_file.parent

            if platform.system() == "Windows":
                os.startfile(log_folder)
            elif platform.system() == "Darwin":
                subprocess.run(["open", log_folder])
            else:
                subprocess.run(["xdg-open", log_folder])

        except Exception as e:
            messagebox.showerror("❌ Erro", f"Não foi possível abrir a pasta:\n{e}")

    def open_output_folder(self):
        """Abre pasta de saída"""
        import os
        import subprocess
        import platform

        output_dir = self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")

    def show_supplier_manager(self):
        """Mostra janela de gerenciamento de fornecedores"""
        if not SUPPLIER_SYSTEM_AVAILABLE or not self.supplier_db:
            messagebox.showerror(
                "Erro",
                "Sistema de fornecedores não está disponível.\n"
                "Verifique se todos os arquivos foram criados corretamente."
            )
            return

        try:
            SupplierManagerWindow(self.root, self.supplier_db_path)
        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de fornecedores: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador:\n{e}")

    def show_category_manager(self):
        """Mostra janela de gerenciamento de categorias"""
        if not CATEGORY_SYSTEM_AVAILABLE or not self.category_manager:
            messagebox.showerror(
                "Erro",
                "Sistema de categorias não está disponível.\n"
                "Verifique se todos os arquivos foram criados corretamente."
            )
            return

        try:
            CategoryManagerWindow(self.root, self.category_manager)
        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de categorias: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador:\n{e}")

    def show_product_manager(self):
        """Mostra dashboard integrado de produtos"""
        try:
            from .components.products_dashboard import ProductsDashboard
            ProductsDashboard(self.root, self.config)
        except Exception as e:
            logger.error(f"Erro ao abrir dashboard de produtos: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o dashboard:\n{e}")

    def show_catalog_manager(self):
        """Mostra gerenciador de catálogo"""
        try:
            from .components.catalog_manager_window import CatalogManagerWindow
            catalog_db_path = self.config.output_dir / "product_catalog.db"

            # Verificar se janela já existe
            if hasattr(self, 'catalog_window') and self.catalog_window and hasattr(self.catalog_window, 'window') and self.catalog_window.window and self.catalog_window.window.winfo_exists():
                self.catalog_window.show()
            else:
                self.catalog_window = CatalogManagerWindow(self.root, catalog_db_path)

        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de catálogo: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador:\n{e}")

    def show_costs_manager(self):
        """Abre gerenciador de custos"""
        try:
            from .components.costs_manager_window import CostsManagerWindow

            # Verificar se janela já existe
            if hasattr(self, 'costs_window') and self.costs_window and hasattr(self.costs_window, 'window') and self.costs_window.window and self.costs_window.window.winfo_exists():
                self.costs_window.show()
            else:
                self.costs_window = CostsManagerWindow(self.root)

        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de custos: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir gerenciador de custos:\n{e}")

    def resolve_supplier_code(self, brand_name: str) -> tuple[int, str]:
        """
        Resolve código e nome oficial do fornecedor baseado no nome da marca
        Usa busca inteligente no banco de dados

        Returns:
            tuple: (codigo_fornecedor, nome_oficial_fornecedor)
        """
        if not brand_name or not brand_name.strip():
            logger.warning("Nome da marca vazio, usando código padrão")
            return 0, "D'Rossi"

        if not self.supplier_db:
            logger.warning("Banco de fornecedores não disponível, usando código padrão")
            return 0, brand_name

        try:
            supplier = self.supplier_db.search_supplier_by_name(brand_name)

            if supplier:
                logger.info(f"Fornecedor encontrado: '{brand_name}' → '{supplier.name}' (código: {supplier.code})")
                return supplier.code, supplier.name
            else:
                logger.warning(f"Fornecedor não encontrado no banco: '{brand_name}' - usando código padrão (0)")
                return 0, brand_name

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor '{brand_name}': {e}")
            return 0, brand_name


    def run(self):
        """Executa a aplicação"""
        self.root.mainloop()

    def close_window_safely(self, window):
        """Fecha janela com proteção contra erros"""
        try:
            if window and window.winfo_exists():
                window.destroy()
        except Exception as e:
            logger.warning(f"⚠️ Erro ao fechar janela: {e}")

    def safe_callback(self, callback_func, *args, **kwargs):
        """Executa callback com proteção contra erros de janela"""
        try:
            if self.winfo_exists():  # Verifica se a janela ainda existe
                return callback_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ Erro em callback: {e}")
            return None

    def initialize_embedded_databases(self):
        """Copia bancos embarcados para pasta de trabalho se não existirem"""
        try:
            # Pasta de destino dos bancos
            db_output_dir = self.config.output_dir
            db_output_dir.mkdir(parents=True, exist_ok=True)

            # Lista de bancos para copiar
            databases_to_copy = [
                ("suppliers.db", "Fornecedores"),
                ("DB_CATEGORIAS.json", "Categorias"),
                ("product_catalog.db", "Catálogo")
            ]

            for db_file, db_name in databases_to_copy:
                # Verificar se existe banco embarcado
                import sys
                if hasattr(sys, '_MEIPASS'):
                    # Executável PyInstaller
                    embedded_db = Path(sys._MEIPASS) / "databases" / db_file
                else:
                    # Desenvolvimento
                    embedded_db = Path("outputs") / db_file

                # Caminho de destino
                target_db = db_output_dir / db_file

                # Só copia se não existir
                if embedded_db.exists() and not target_db.exists():
                    import shutil
                    shutil.copy2(embedded_db, target_db)
                    logger.info(f"✅ Banco {db_name} copiado: {embedded_db} → {target_db}")
                elif target_db.exists():
                    logger.info(f"ℹ️ Banco {db_name} já existe: {target_db}")

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar bancos embarcados: {e}")

# ✅ FUNÇÃO MAIN FORA DA CLASSE (0 ESPAÇOS DE INDENTAÇÃO)
def main():
    """Função principal"""
    try:
        app = MainWindow()
        app.run()
    except Exception as e:
        logger.error(f"Erro fatal na aplicação: {e}")
        messagebox.showerror("Erro Fatal", f"Erro ao iniciar aplicação:\n{e}")

# ✅ BLOCO IF FORA DA CLASSE (0 ESPAÇOS DE INDENTAÇÃO)
if __name__ == "__main__":
    main()