""""Interface gráfica principal com CustomTkinter"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import asyncio
import threading
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

    def setup_ui(self):
        """Configura a interface"""
        self.root = ctk.CTk()
        self.root.title("📊 Cadastro Automático D'Rossi v2.1")
        self.root.minsize(800, 700)
        # ✅ VARIÁVEIS DA INTERFACE (APÓS CRIAR A JANELA PRINCIPAL)
        self.brand_var = tk.StringVar(value=self.config.default_brand)
        self.enable_exception_prazo_var = tk.BooleanVar(value=self.config.enable_exception_prazo)
        self.exception_prazo_days_var = tk.StringVar(value=str(self.config.exception_prazo_days))
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
        self.create_floating_color_button()

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
                        except Exception:
                            pass
                    elif window and hasattr(window, 'destroy'):
                        try:
                            window.destroy()
                        except Exception:
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
            except Exception:
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

        # ✅ ADICIONAR AQUI - NOVA SEÇÃO: Exceção de Prazo
        exception_prazo_frame = ctk.CTkFrame(config_grid, fg_color="transparent")
        exception_prazo_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(15, 0))

        self.enable_exception_prazo_checkbox = ctk.CTkCheckBox(
            exception_prazo_frame,
            text="Exceção de Prazo para Entrega",
            variable=self.enable_exception_prazo_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_exception_prazo_fields
        )
        self.enable_exception_prazo_checkbox.pack(anchor="w", pady=(0, 10))

        # Campo de entrada para o prazo de exceção
        exception_input_frame = ctk.CTkFrame(exception_prazo_frame, fg_color="transparent")
        exception_input_frame.pack(fill="x", padx=(25, 0), pady=(0, 10))

        ctk.CTkLabel(
            exception_input_frame,
            text="Prazo de Exceção (dias):",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", anchor="w", padx=(0, 10))

        self.exception_prazo_entry = ctk.CTkEntry(
            exception_input_frame,
            textvariable=self.exception_prazo_days_var,
            placeholder_text="0",
            width=80
        )
        self.exception_prazo_entry.pack(side="left", anchor="w")

        # Info
        ctk.CTkLabel(
            exception_prazo_frame,
            text="ℹ️ Se habilitado, este prazo será usado para todos os produtos, ignorando o do fornecedor.",
            font=ctk.CTkFont(size=11),
            text_color=("gray60", "gray40"),
            wraplength=600
        ).pack(anchor="w", pady=(5, 0))

        # Chamar a função para definir o estado inicial dos campos
        self.toggle_exception_prazo_fields()

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

    def toggle_exception_prazo_fields(self):
        """Ativa/desativa campo de prazo de exceção"""
        state = "normal" if self.enable_exception_prazo_var.get() else "disabled"
        self.exception_prazo_entry.configure(state=state)

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

    def create_floating_color_button(self):
        """Cria botão flutuante de personalização de cores"""
        # ✅ FRAME FLUTUANTE NO CANTO INFERIOR DIREITO
        self.floating_frame = ctk.CTkFrame(
            self.root,
            width=60,
            height=60,
            corner_radius=30,
            fg_color=("gray75", "gray25")
        )
        self.floating_frame.place(relx=0.98, rely=0.95, anchor="se")
        self.floating_frame.pack_propagate(False)

        # ✅ BOTÃO DE PALHETA DE CORES
        self.color_palette_btn = ctk.CTkButton(
            self.floating_frame,
            text="🎨",
            width=50,
            height=50,
            corner_radius=25,
            font=ctk.CTkFont(size=20),
            command=self.show_color_customization,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40")
        )
        self.color_palette_btn.pack(expand=True, fill="both", padx=5, pady=5)

    def show_color_customization(self):
        """Mostra janela de personalização de cores - APENAS COR PRINCIPAL E FONTE"""
        try:
            # ✅ JANELA DE PERSONALIZAÇÃO
            color_window = ctk.CTkToplevel(self.root)
            color_window.title("🎨 Personalização de Cores")
            color_window.geometry("500x600")
            color_window.transient(self.root)
            color_window.grab_set()

            # ✅ CENTRALIZAR JANELA
            color_window.update_idletasks()
            x = (color_window.winfo_screenwidth() // 2) - (500 // 2)
            y = (color_window.winfo_screenheight() // 2) - (600 // 2)
            color_window.geometry(f"500x600+{x}+{y}")

            # ✅ HEADER
            header_frame = ctk.CTkFrame(color_window)
            header_frame.pack(fill="x", padx=20, pady=(20, 10))

            ctk.CTkLabel(
                header_frame,
                text="🎨 Personalização de Cores",
                font=ctk.CTkFont(size=24, weight="bold")
            ).pack(pady=15)

            ctk.CTkLabel(
                header_frame,
                text="Personalize as cores do sistema",
                font=ctk.CTkFont(size=14),
                text_color=("gray60", "gray40")
            ).pack(pady=(0, 15))

            # ✅ SEÇÃO 1: COR PRINCIPAL DO APP
            main_color_frame = ctk.CTkFrame(color_window)
            main_color_frame.pack(fill="x", padx=20, pady=(0, 15))

            ctk.CTkLabel(
                main_color_frame,
                text="🎨 Cor Principal do App",
                font=ctk.CTkFont(size=18, weight="bold"),
                anchor="w"
            ).pack(fill="x", padx=20, pady=(20, 10))

            # ✅ CORES PREDEFINIDAS PRINCIPAIS
            main_colors_grid = ctk.CTkFrame(main_color_frame, fg_color="transparent")
            main_colors_grid.pack(fill="x", padx=20, pady=(0, 15))

            main_colors = [
                ("🔵 Azul", "#1f538d"),
                ("🟢 Verde", "#2fa572"),
                ("🟣 Roxo", "#7b2cbf"),
                ("🟡 Amarelo", "#FFD700"),
                ("🔴 Vermelho", "#DC143C"),
                ("🟠 Laranja", "#FF8C00"),
                ("⚫ Preto", "#2b2b2b"),
                ("🟤 Marrom", "#8B4513")
            ]

            for i, (name, color_hex) in enumerate(main_colors):
                row = i // 4
                col = i % 4

                color_btn = ctk.CTkButton(
                    main_colors_grid,
                    text=name,
                    width=100,
                    height=40,
                    font=ctk.CTkFont(size=11),
                    fg_color=color_hex,
                    hover_color=self._darken_color(color_hex),
                    command=lambda c=color_hex: self.apply_main_color(c)
                )
                color_btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")

            # ✅ CONFIGURAR GRID
            for i in range(4):
                main_colors_grid.grid_columnconfigure(i, weight=1)

            # ✅ BOTÃO PERSONALIZADO PRINCIPAL
            ctk.CTkButton(
                main_color_frame,
                text="🎨 Escolher Cor Principal Personalizada",
                command=self.choose_custom_main_color,
                height=40,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(fill="x", padx=20, pady=(15, 20))

            # ✅ SEÇÃO 2: COR DA FONTE/TEXTO
            font_color_frame = ctk.CTkFrame(color_window)
            font_color_frame.pack(fill="x", padx=20, pady=(0, 15))

            ctk.CTkLabel(
                font_color_frame,
                text="📝 Cor da Fonte/Texto",
                font=ctk.CTkFont(size=18, weight="bold"),
                anchor="w"
            ).pack(fill="x", padx=20, pady=(20, 10))

            # ✅ CORES PREDEFINIDAS PARA FONTE
            font_colors_grid = ctk.CTkFrame(font_color_frame, fg_color="transparent")
            font_colors_grid.pack(fill="x", padx=20, pady=(0, 15))

            font_colors = [
                ("⚪ Branco", "#FFFFFF"),
                ("⚫ Preto", "#000000"),
                ("🔵 Azul Escuro", "#1e3a8a"),
                ("🟢 Verde Escuro", "#166534"),
                ("🔴 Vermelho Escuro", "#991b1b"),
                ("🟣 Roxo Escuro", "#581c87"),
                ("🟤 Marrom Escuro", "#451a03"),
                ("🔘 Cinza", "#6b7280")
            ]

            for i, (name, color_hex) in enumerate(font_colors):
                row = i // 4
                col = i % 4

                # ✅ COR DE FUNDO CONTRASTANTE PARA VISUALIZAR A COR DA FONTE
                bg_color = "#FFFFFF" if color_hex in ["#FFFFFF", "#FFD700"] else "#2b2b2b"

                color_btn = ctk.CTkButton(
                    font_colors_grid,
                    text=name,
                    width=100,
                    height=40,
                    font=ctk.CTkFont(size=11),
                    fg_color=bg_color,
                    text_color=color_hex,
                    hover_color=self._darken_color(bg_color),
                    command=lambda c=color_hex: self.apply_font_color(c)
                )
                color_btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")

            # ✅ CONFIGURAR GRID
            for i in range(4):
                font_colors_grid.grid_columnconfigure(i, weight=1)

            # ✅ BOTÃO PERSONALIZADO FONTE
            ctk.CTkButton(
                font_color_frame,
                text="📝 Escolher Cor da Fonte Personalizada",
                command=self.choose_custom_font_color,
                height=40,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(fill="x", padx=20, pady=(15, 20))

            # ✅ BOTÕES DE AÇÃO
            action_frame = ctk.CTkFrame(color_window)
            action_frame.pack(fill="x", padx=20, pady=(0, 20))

            buttons_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
            buttons_frame.pack(fill="x", padx=20, pady=15)

            # ✅ RESET E FECHAR
            ctk.CTkButton(
                buttons_frame,
                text="🔄 Resetar Padrão",
                command=self.reset_default_colors,
                width=140,
                height=40
            ).pack(side="left", padx=(0, 10))

            ctk.CTkButton(
                buttons_frame,
                text="✅ Fechar",
                command=color_window.destroy,
                width=140,
                height=40
            ).pack(side="right")

        except Exception as e:
            logger.error(f"Erro ao abrir personalização de cores: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao abrir personalização:\n{e}")

    def apply_main_color(self, color_hex: str):
        """Aplica cor principal COMPLETA - fundo, janelas e botões com tons"""
        try:
            logger.info(f"🎨 Aplicando cor principal completa: {color_hex}")

            # ✅ CALCULAR TONS DA COR
            base_color = color_hex  # Cor original para fundos
            darker_color = self._darken_color(color_hex, 0.8)  # 20% mais escuro para botões
            lighter_color = self._lighten_color(color_hex, 0.9)  # 10% mais claro para hover

            logger.info("🎨 Tons calculados:")
            logger.info(f"   Base (fundos): {base_color}")
            logger.info(f"   Escuro (botões): {darker_color}")
            logger.info(f"   Claro (hover): {lighter_color}")

            # ✅ 1. APLICAR COR DE FUNDO DA JANELA PRINCIPAL
            if hasattr(self, 'root'):
                self.root.configure(fg_color=base_color)

            # ✅ 2. ATUALIZAR TODOS OS FRAMES PRINCIPAIS
            main_frames = [
                'main_frame'
            ]

            for frame_name in main_frames:
                if hasattr(self, frame_name):
                    frame = getattr(self, frame_name)
                    frame.configure(fg_color=base_color)

            # ✅ 3. ATUALIZAR FRAMES DE SEÇÕES COM TOM MAIS CLARO
            self._update_section_frames(lighter_color)

            # ✅ 4. ATUALIZAR BOTÕES COM TOM MAIS ESCURO
            self._update_all_buttons_with_darker_tone(darker_color, lighter_color)

            # ✅ 5. ATUALIZAR PROGRESS BAR
            if hasattr(self, 'progress_bar'):
                self.progress_bar.configure(progress_color=darker_color)

            # ✅ 6. ATUALIZAR CHECKBOXES E COMBOBOXES
            self._update_interactive_elements(darker_color)

            # ✅ 7. FORÇAR ATUALIZAÇÃO COMPLETA
            self._force_complete_interface_update()

            messagebox.showinfo("✅ Sucesso",
                                f"Tema completo aplicado!\n\n🎨 Cor base: {base_color}\n🔘 Botões: {darker_color}")

        except Exception as e:
            logger.error(f"Erro ao aplicar cor principal: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao aplicar cor:\n{e}")

    def _update_section_frames(self, lighter_color: str):
        """Atualiza frames de seções com cor mais clara"""
        try:
            def update_frames_recursive(widget):
                try:
                    # ✅ SE É UM FRAME CTK, ATUALIZAR
                    if isinstance(widget, ctk.CTkFrame):
                        # ✅ NÃO ATUALIZAR FRAMES TRANSPARENTES
                        try:
                            current_fg = widget.cget("fg_color")
                            if current_fg != "transparent":
                                widget.configure(fg_color=lighter_color)
                        except Exception:
                            widget.configure(fg_color=lighter_color)

                    # ✅ RECURSIVAMENTE VERIFICAR FILHOS
                    if hasattr(widget, 'winfo_children'):
                        for child in widget.winfo_children():
                            update_frames_recursive(child)

                except Exception as e:
                    logger.debug(f"Erro ao atualizar frame: {e}")

            # ✅ APLICAR A PARTIR DA JANELA PRINCIPAL
            if hasattr(self, 'root'):
                update_frames_recursive(self.root)

            logger.info(f"🎨 Frames atualizados com cor: {lighter_color}")

        except Exception as e:
            logger.error(f"Erro ao atualizar frames: {e}")

    def _update_all_buttons_with_darker_tone(self, darker_color: str, hover_color: str):
        """Atualiza TODOS os botões com tom mais escuro"""
        try:
            def update_buttons_recursive(widget):
                try:
                    # ✅ SE É UM BOTÃO CTK, ATUALIZAR
                    if isinstance(widget, ctk.CTkButton):
                        button_text = str(widget.cget("text")).lower()
                        # ✅ PULAR APENAS BOTÕES DE FECHAR
                        if "fechar" not in button_text and "✅" not in button_text:
                            widget.configure(
                                fg_color=darker_color,
                                hover_color=hover_color
                            )

                    # ✅ RECURSIVAMENTE VERIFICAR FILHOS
                    if hasattr(widget, 'winfo_children'):
                        for child in widget.winfo_children():
                            update_buttons_recursive(child)

                except Exception as e:
                    logger.debug(f"Erro ao atualizar botão: {e}")

            # ✅ APLICAR A PARTIR DA JANELA PRINCIPAL
            if hasattr(self, 'root'):
                update_buttons_recursive(self.root)

            logger.info(f"🎨 Botões atualizados - Cor: {darker_color}, Hover: {hover_color}")

        except Exception as e:
            logger.error(f"Erro ao atualizar botões: {e}")

    def _update_interactive_elements(self, darker_color: str):
        """Atualiza checkboxes e comboboxes"""
        try:
            # ✅ CHECKBOXES
            checkboxes = [
                'enable_pricing_checkbox',
                'send_email_checkbox',
                'enable_exception_prazo_checkbox',
                'apply_90_cents_checkbox'
            ]

            for checkbox_name in checkboxes:
                if hasattr(self, checkbox_name):
                    checkbox = getattr(self, checkbox_name)
                    checkbox.configure(fg_color=darker_color)

            # ✅ COMBOBOXES
            comboboxes = [
                'sheet_combobox',
                'pricing_mode_combo'
            ]

            for combo_name in comboboxes:
                if hasattr(self, combo_name):
                    combo = getattr(self, combo_name)
                    combo.configure(button_color=darker_color)

            logger.info(f"🎨 Elementos interativos atualizados com cor: {darker_color}")

        except Exception as e:
            logger.error(f"Erro ao atualizar elementos interativos: {e}")

    def _lighten_color(self, color_hex: str, factor: float = 0.9) -> str:
        """Clareia uma cor"""
        try:
            # Remove o # se presente
            color_hex = color_hex.lstrip('#')

            # Converte para RGB
            r = int(color_hex[0:2], 16)
            g = int(color_hex[2:4], 16)
            b = int(color_hex[4:6], 16)

            # Clareia (move em direção ao branco)
            r = int(r + (255 - r) * (1 - factor))
            g = int(g + (255 - g) * (1 - factor))
            b = int(b + (255 - b) * (1 - factor))

            # Garante que não ultrapasse 255
            r = min(255, r)
            g = min(255, g)
            b = min(255, b)

            # Converte de volta para hex
            return f"#{r:02x}{g:02x}{b:02x}"

        except Exception:
            return "#f0f0f0"  # Cor padrão clara em caso de erro

    def _force_complete_interface_update(self):
        """Força atualização COMPLETA da interface"""
        try:
            # ✅ MÚLTIPLAS ATUALIZAÇÕES PARA GARANTIR RENDERIZAÇÃO
            self.root.update()
            self.root.update_idletasks()

            # ✅ PEQUENAS PAUSAS PARA GARANTIR RENDERIZAÇÃO COMPLETA
            self.root.after(10, lambda: self.root.update_idletasks())
            self.root.after(50, lambda: self.root.update())

            logger.info("🎨 Interface completamente atualizada")

        except Exception as e:
            logger.debug(f"Erro ao forçar atualização completa: {e}")

    def _update_all_buttons_recursive(self, color_hex: str):
        """Busca e atualiza TODOS os botões da interface"""
        try:
            def update_widget_recursive(widget):
                try:
                    # ✅ SE É UM BOTÃO CTK, ATUALIZAR
                    if isinstance(widget, ctk.CTkButton):
                        # ✅ PULAR APENAS O BOTÃO DE FECHAR (SE EXISTIR)
                        button_text = str(widget.cget("text")).lower()
                        if "fechar" not in button_text and "✅" not in button_text:
                            widget.configure(fg_color=color_hex)

                    # ✅ RECURSIVAMENTE VERIFICAR FILHOS
                    if hasattr(widget, 'winfo_children'):
                        for child in widget.winfo_children():
                            update_widget_recursive(child)

                except Exception as e:
                    # ✅ IGNORAR ERROS DE WIDGETS ESPECÍFICOS
                    logger.debug(f"Erro ao atualizar widget: {e}")

            # ✅ APLICAR A PARTIR DA JANELA PRINCIPAL
            if hasattr(self, 'root'):
                update_widget_recursive(self.root)

            logger.info(f"🎨 Todos os botões atualizados com cor: {color_hex}")

        except Exception as e:
            logger.error(f"Erro ao atualizar botões recursivamente: {e}")

    def _force_interface_update(self):
        """Força atualização completa da interface"""
        try:
            self.root.update()
            self.root.update_idletasks()

            # ✅ PEQUENA PAUSA PARA GARANTIR RENDERIZAÇÃO
            self.root.after(10, lambda: self.root.update_idletasks())

        except Exception as e:
            logger.debug(f"Erro ao forçar atualização: {e}")

    def apply_font_color(self, color_hex: str):
        """Aplica cor da fonte/texto"""
        try:
            logger.info(f"📝 Aplicando cor da fonte: {color_hex}")

            # ✅ ATUALIZAR COR DOS TEXTOS PRINCIPAIS
            def update_text_colors(widget):
                try:
                    if isinstance(widget, ctk.CTkLabel):
                        widget.configure(text_color=color_hex)

                    # Recursivamente verificar filhos
                    if hasattr(widget, 'winfo_children'):
                        for child in widget.winfo_children():
                            update_text_colors(child)

                except Exception:
                    pass

            # ✅ APLICAR A PARTIR DA JANELA PRINCIPAL
            if hasattr(self, 'root'):
                update_text_colors(self.root)

            messagebox.showinfo("✅ Sucesso", f"Cor da fonte aplicada!\n\n📝 Cor: {color_hex}")

        except Exception as e:
            logger.error(f"Erro ao aplicar cor da fonte: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao aplicar cor da fonte:\n{e}")


    def choose_custom_font_color(self):
        """Escolher cor da fonte personalizada"""
        try:
            from tkinter import colorchooser

            color = colorchooser.askcolor(
                title="📝 Escolher Cor da Fonte",
                color="#FFFFFF"
            )

            if color[1]:
                self.apply_font_color(color[1])

        except Exception as e:
            logger.error(f"Erro ao escolher cor da fonte: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao escolher cor da fonte:\n{e}")

    def reset_default_colors(self):
        """Reseta para cores padrão"""
        try:
            result = messagebox.askyesno(
                "🔄 Resetar Cores",
                "Deseja resetar todas as cores para o padrão?"
            )

            if result:
                # ✅ APLICAR CORES PADRÃO
                self.apply_main_color("#1f538d")  # Azul padrão
                self.apply_font_color("#FFFFFF")  # Branco padrão

                messagebox.showinfo("✅ Sucesso", "Cores resetadas para o padrão!")

        except Exception as e:
            logger.error(f"Erro ao resetar cores: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao resetar cores:\n{e}")


    def _update_all_interface_colors(self, color_hex: str):
        """Atualiza TODAS as cores da interface INSTANTANEAMENTE (VERSÃO SEGURA)"""
        try:
            # ✅ 1. ATUALIZAR BOTÃO FLUTUANTE
            if hasattr(self, 'color_palette_btn'):
                self.color_palette_btn.configure(fg_color=color_hex)

            # ✅ 2. ATUALIZAR BOTÃO PRINCIPAL DE PROCESSAMENTO (SEM TRAVAR)
            if hasattr(self, 'process_button'):
                current_state = self.process_button.cget("state")
                self.process_button.configure(fg_color=color_hex)
                self.process_button.configure(state=current_state)  # Manter estado

            # ✅ 3. ATUALIZAR PROGRESS BAR
            if hasattr(self, 'progress_bar'):
                self.progress_bar.configure(progress_color=color_hex)


            logger.info(f"🎨 Cores da interface atualizadas com segurança: {color_hex}")

        except Exception as e:
            logger.error(f"Erro ao atualizar cores da interface: {e}")



    def choose_custom_main_color(self):
        """Escolher cor principal personalizada"""
        try:
            from tkinter import colorchooser

            color = colorchooser.askcolor(
                title="🎨 Escolher Cor Principal",
                color="#1f538d"
            )

            if color[1]:
                self.apply_main_color(color[1])
                # ✅ FORÇAR ATUALIZAÇÃO ADICIONAL
                self._force_interface_update()

        except Exception as e:
            logger.error(f"Erro ao escolher cor principal: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao escolher cor:\n{e}")

    def reset_default_colors(self): # noqa: F811
            """Reseta para cores padrão"""
            try:
                result = messagebox.askyesno(
                    "🔄 Resetar Cores",
                    "Deseja resetar todas as cores para o padrão?\n\nIsso irá aplicar o tema azul padrão."
                )

                if result:
                    ctk.set_default_color_theme("blue")
                    ctk.set_appearance_mode("dark")
                    logger.info("✅ Cores resetadas para o padrão")
                    messagebox.showinfo("✅ Sucesso", "Cores resetadas para o padrão!")

            except Exception as e:
                logger.error(f"Erro ao resetar cores: {e}")
                messagebox.showerror("❌ Erro", f"Erro ao resetar cores:\n{e}")

    def _update_interface_colors(self, color_hex: str):
            """Atualiza cores da interface atual"""
            try:
                # ✅ ATUALIZAR BOTÃO FLUTUANTE
                if hasattr(self, 'color_palette_btn'):
                    self.color_palette_btn.configure(fg_color=color_hex)

                logger.info(f"🎨 Interface atualizada com cor: {color_hex}")

            except Exception as e:
                logger.error(f"Erro ao atualizar interface: {e}")

    def _darken_color(self, color_hex: str, factor: float = 0.8) -> str:
            """Escurece uma cor para efeito hover"""
            try:
                # Remove o # se presente
                color_hex = color_hex.lstrip('#')

                # Converte para RGB
                r = int(color_hex[0:2], 16)
                g = int(color_hex[2:4], 16)
                b = int(color_hex[4:6], 16)

                # Escurece
                r = int(r * factor)
                g = int(g * factor)
                b = int(b * factor)

                # Converte de volta para hex
                return f"#{r:02x}{g:02x}{b:02x}"

            except Exception:
                return "#1f538d"  # Cor padrão em caso de erro

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
                except Exception:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Erro",
                        f"❌ Erro ao testar conexão:\n{str(e)}" # noqa: F821
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

            # ✅ SALVAR NOVO PRAZO DE EXCEÇÃO
            self.config.enable_exception_prazo = self.enable_exception_prazo_var.get()
            try:
                self.config.exception_prazo_days = int(self.exception_prazo_days_var.get())
            except ValueError:
                self.config.exception_prazo_days = 0
                logger.warning(
                    f"Valor inválido para prazo de exceção: '{self.exception_prazo_days_var.get()}', usando 0.")

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
                messagebox.showerror("Erro",
                                     "Selecione a planilha de custos ou desabilite a precificação automática")
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
            brand_name = self.brand_var.get() or "D'Rossi"  # ✅ DEFINIR BRAND_NAME PRIMEIRO
            self.config.default_brand = brand_name

            # ✅ ATUALIZAR CONFIGURAÇÃO COM OS VALORES DO PRAZO DE EXCEÇÃO
            self.config.enable_exception_prazo = self.enable_exception_prazo_var.get()
            try:
                self.config.exception_prazo_days = int(self.exception_prazo_days_var.get())
            except ValueError:
                self.config.exception_prazo_days = 0
                logger.warning(
                    f"Valor inválido para prazo de exceção durante processamento: '{self.exception_prazo_days_var.get()}', usando 0.")

            logger.info(
                f"Configuração de exceção de prazo: Habilitado={self.config.enable_exception_prazo}, Dias={self.config.exception_prazo_days}")

            supplier_code, official_brand_name = self.resolve_supplier_code(brand_name)  # ✅ AGORA FUNCIONA
            self.config.supplier_code = supplier_code
            self.config.default_brand = official_brand_name

            logger.info("Configuração de fornecedor:")
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

                logger.info("Precificação automática habilitada:")
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
                self.root.after(0, lambda msg=error_msg: messagebox.showerror("Erro",
                                                                              f"Erro no processamento:\n{msg}"))
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
                except Exception:
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
                f"📈 Taxa de sucesso: {result.success_rate * 100:.1f}%\n\n"
                f"📁 Arquivo salvo em:\n{result.output_file}"
            )
            messagebox.showinfo("Sucesso!", message)
        else:
            error_msg = "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                error_msg += f"\n... e mais {len(result.errors) - 5} erros"

            messagebox.showerror(
                "Erro no Processamento",
                f"❌ Falha no processamento:\n\n{error_msg}"
            )

    def show_logs(self):
        """Mostra logs simples"""
        try:
            messagebox.showinfo("📋 Logs", "Funcionalidade de logs em desenvolvimento")
        except Exception as e:
            logger.error(f"Erro ao abrir logs: {e}")

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
            if hasattr(self, 'catalog_window') and self.catalog_window and hasattr(self.catalog_window,
                                                                                   'window') and self.catalog_window.window and self.catalog_window.window.winfo_exists():
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
                if hasattr(self, 'costs_window') and self.costs_window and hasattr(self.costs_window,
                                                                                   'window') and self.costs_window.window and self.costs_window.window.winfo_exists():
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

    def main(self):
        """Função principal com tratamento de interrupção"""
        try:
            app = MainWindow()
            app.run()
        except KeyboardInterrupt:
            logger.info("🛑 Aplicação interrompida pelo usuário (Ctrl+C)")
            print("\n🛑 Aplicação fechada pelo usuário")
        except Exception as e:
            logger.error(f"Erro fatal na aplicação: {e}")
            messagebox.showerror("Erro Fatal", f"Erro ao iniciar aplicação:\n{e}")
        finally:
            print("👋 Aplicação finalizada")

    if __name__ == "__main__":
        main()