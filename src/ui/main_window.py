"""Interface gráfica principal com CustomTkinter"""

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
    SUPPLIER_SYSTEM_AVAILABLE = True
except ImportError:
    SupplierManagerWindow = None
    SUPPLIER_SYSTEM_AVAILABLE = False

try:
    from .components.category_manager_window import CategoryManagerWindow
    from ..services.category_manager import CategoryManager
    CATEGORY_SYSTEM_AVAILABLE = True
except ImportError:
    CategoryManagerWindow = None
    CategoryManager = None
    CATEGORY_SYSTEM_AVAILABLE = False

# ✅ NOVO: Robô Athos (tela)
try:
    from .athos_window import AthosWindow
    ATHOS_SYSTEM_AVAILABLE = True
except ImportError:
    AthosWindow = None
    ATHOS_SYSTEM_AVAILABLE = False

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

        # ✅ Reflete status do banco de fornecedores no UI
        try:
            if hasattr(self.processor, 'is_supplier_db_available'):
                self.supplier_db_available = bool(self.processor.is_supplier_db_available())
            self.supplier_status_message = getattr(self.processor, 'supplier_status_message', '') or ''
        except Exception:
            self.supplier_db_available = False
            self.supplier_status_message = 'Indisponível'
        # ✅ Caminho esperado do banco de fornecedores (para UI/diagnóstico)
        self.supplier_db_path = self.config.output_dir / "suppliers.db"

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
        self.supplier_manager_window = None

        # ✅ NOVO: janela do Robô Athos
        self.athos_window = None

        # ✅ CONFIGURAR UI POR ÚLTIMO
        self.setup_ui()

    def initialize_supplier_database(self):
        """(Legado) Inicialização automática de fornecedores.

        ✅ Agora o banco de fornecedores é inicializado dentro do ProductProcessor de forma
        resiliente (não quebra se faltar sqlite3/arquivo/permissão).
        Mantido aqui apenas por compatibilidade.
        """
        return

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

        # ✅ PRAZO DE EXCEÇÃO (NOVO)
        self.enable_exception_prazo_var = tk.BooleanVar(value=getattr(self.config, "enable_exception_prazo", False))
        self.exception_prazo_days_var = tk.StringVar(value=str(getattr(self.config, "exception_prazo_days", 0)))

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

        # ✅ Atualiza indicadores/estado de botões conforme disponibilidade de módulos
        self.refresh_system_status()

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
            for attr_name in ['log_viewer', 'catalog_window', 'costs_window', 'progress_dialog', 'athos_window']:
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

    # =========================
    # SEÇÕES (Arquivo/Config/Pricing/E-mail/Processamento)
    # =========================
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

        # Planilha de origem
        self.create_file_input(
            files_frame,
            "Planilha de Origem *",
            "Selecione a planilha Excel com os dados dos produtos...",
            "origin_file"
        )

        # ✅ Dropdown de abas
        sheet_frame = ctk.CTkFrame(files_frame, fg_color="transparent")
        sheet_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            sheet_frame,
            text="📄 Aba a processar *",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        self.sheet_combobox = ctk.CTkComboBox(
            sheet_frame,
            values=["Selecione um arquivo primeiro."],
            state="readonly"
        )
        self.sheet_combobox.pack(fill="x", pady=(0, 5))

        self.sheet_status_label = ctk.CTkLabel(
            sheet_frame,
            text="Selecione um arquivo para listar as abas.",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40"),
            anchor="w"
        )
        self.sheet_status_label.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            sheet_frame,
            text="🔄 Atualizar Abas",
            command=self.refresh_sheet_list,
            height=34
        ).pack(anchor="w")

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

        # Marca (fornecedor)
        brand_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        brand_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            brand_frame,
            text="🏷️ Marca / Fornecedor",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        brand_entry = ctk.CTkEntry(
            brand_frame,
            textvariable=self.brand_var,
            placeholder_text="Ex: D'Rossi"
        )
        brand_entry.pack(fill="x", pady=(0, 10))

        # Prazo de exceção
        prazo_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        prazo_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            prazo_frame,
            text="⏱️ Prazo de Exceção (opcional)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 8))

        row = ctk.CTkFrame(prazo_frame, fg_color="transparent")
        row.pack(fill="x")

        self.enable_exception_prazo_chk = ctk.CTkCheckBox(
            row,
            text="Aplicar prazo fixo de exceção para todos os itens",
            variable=self.enable_exception_prazo_var,
            command=self.toggle_exception_prazo_fields
        )
        self.enable_exception_prazo_chk.pack(side="left", padx=(0, 15))

        self.exception_prazo_entry = ctk.CTkEntry(
            row,
            width=120,
            textvariable=self.exception_prazo_days_var,
            placeholder_text="dias"
        )
        self.exception_prazo_entry.pack(side="left")

        ctk.CTkLabel(
            row,
            text="dias",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        ).pack(side="left", padx=(6, 0))

        self.toggle_exception_prazo_fields()

    def toggle_exception_prazo_fields(self):
        """Habilita/Desabilita o campo de prazo de exceção"""
        try:
            enabled = bool(self.enable_exception_prazo_var.get())
            state = "normal" if enabled else "disabled"
            self.exception_prazo_entry.configure(state=state)
        except Exception:
            pass

    def create_pricing_section(self):
        """Seção de precificação"""
        pricing_frame = ctk.CTkFrame(self.main_frame)
        pricing_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            pricing_frame,
            text="💰 Precificação",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        # Ativar/desativar precificação
        self.enable_pricing_var = tk.BooleanVar(value=getattr(self.config, "enable_pricing", False))

        chk = ctk.CTkCheckBox(
            pricing_frame,
            text="Ativar precificação automática",
            variable=self.enable_pricing_var,
            command=self.toggle_pricing_fields
        )
        chk.pack(anchor="w", padx=20, pady=(0, 10))

        # Planilha de custos
        self.create_file_input(
            pricing_frame,
            "Planilha de Custos",
            "Selecione a planilha Excel com os custos...",
            "cost_file"
        )

        self.toggle_pricing_fields()

    def toggle_pricing_fields(self):
        """Habilita/Desabilita campos de pricing"""
        try:
            enabled = bool(self.enable_pricing_var.get())
            state = "normal" if enabled else "disabled"
            if hasattr(self, "cost_file_var"):
                # entry do arquivo de custos (CTkEntry)
                # como é criado dentro create_file_input, não guardamos o widget entry - mas manter var basta
                pass
        except Exception:
            pass

    def create_email_section(self):
        """Seção de e-mail"""
        email_frame = ctk.CTkFrame(self.main_frame)
        email_frame.pack(fill="x", pady=(0, 20))

        section_title = ctk.CTkLabel(
            email_frame,
            text="📧 Relatório por E-mail",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        section_title.pack(fill="x", padx=20, pady=(20, 15))

        self.send_email_var = tk.BooleanVar(value=bool(self.config.email))
        send_email_chk = ctk.CTkCheckBox(
            email_frame,
            text="Enviar relatório por e-mail ao concluir",
            variable=self.send_email_var,
            command=self.toggle_email_fields
        )
        send_email_chk.pack(anchor="w", padx=20, pady=(0, 10))

        # Campos
        self.email_username_var = tk.StringVar(value=self.config.email.username if self.config.email else "")
        self.email_password_var = tk.StringVar(value=self.config.email.password if self.config.email else "")
        self.email_recipients_var = tk.StringVar(value=",".join(self.config.email.to_addrs) if self.config.email else "")

        grid = ctk.CTkFrame(email_frame, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(grid, text="E-mail:", width=100, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ctk.CTkEntry(grid, textvariable=self.email_username_var, placeholder_text="seu@email.com").grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(grid, text="Senha app:", width=100, anchor="w").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ctk.CTkEntry(grid, textvariable=self.email_password_var, show="*", placeholder_text="senha de app").grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(grid, text="Destinatários:", width=100, anchor="w").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ctk.CTkEntry(grid, textvariable=self.email_recipients_var, placeholder_text="email1, email2, ...").grid(row=2, column=1, sticky="ew", pady=(0, 8))

        grid.grid_columnconfigure(1, weight=1)

        btns = ctk.CTkFrame(email_frame, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 20))

        self.test_email_btn = ctk.CTkButton(btns, text="🧪 Testar Conexão", command=self.test_email_connection, width=160)
        self.test_email_btn.pack(side="left", padx=(0, 10))

        ctk.CTkButton(btns, text="💾 Salvar Config", command=self.save_email_config, width=160).pack(side="left")

        self.toggle_email_fields()

    def toggle_email_fields(self):
        """Habilita/Desabilita campos de e-mail"""
        enabled = bool(self.send_email_var.get())
        state = "normal" if enabled else "disabled"
        try:
            self.test_email_btn.configure(state=state)
        except Exception:
            pass


    def refresh_system_status(self):
        """Atualiza a interface conforme disponibilidade dos subsistemas."""
        # Status Fornecedores
        status_f = getattr(self, "supplier_status_var", None)
        btn_f = getattr(self, "btn_fornecedores", None)
        if getattr(self, "supplier_db_available", False):
            if status_f:
                status_f.set("✅ Fornecedores: OK")
            if btn_f:
                btn_f.configure(state="normal")
        else:
            reason = getattr(self, "supplier_db_unavailable_reason", "Indisponível")
            if status_f:
                status_f.set(f"⚠️ Fornecedores: Indisponível — {reason}")
            if btn_f:
                btn_f.configure(state="disabled")

        # Status Categorias
        status_c = getattr(self, "category_status_var", None)
        btn_c = getattr(self, "btn_categorias", None)
        if getattr(self, "category_manager_available", False):
            if status_c:
                status_c.set("✅ Categorias: OK")
            if btn_c:
                btn_c.configure(state="normal")
        else:
            reason = getattr(self, "category_manager_unavailable_reason", "Indisponível")
            if status_c:
                status_c.set(f"⚠️ Categorias: Indisponível — {reason}")
            if btn_c:
                btn_c.configure(state="disabled")

        # Status Robô Athos
        status_a = getattr(self, "athos_status_var", None)
        btn_a = getattr(self, "btn_athos", None)
        if getattr(self, "athos_available", False):
            if status_a:
                status_a.set("✅ Robô Athos: OK")
            if btn_a:
                btn_a.configure(state="normal")
        else:
            reason = getattr(self, "athos_unavailable_reason", "Indisponível")
            if status_a:
                status_a.set(f"⚠️ Robô Athos: Indisponível — {reason}")
            if btn_a:
                btn_a.configure(state="disabled")


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
        self.btn_fornecedores = ctk.CTkButton(
            first_row,
            text="🗄️ Fornecedores",
            command=self.show_supplier_manager,
            height=40,
            width=130
        )
        self.btn_fornecedores.pack(side="left", padx=(0, 10))

        self.btn_categorias = ctk.CTkButton(
            first_row,
            text="🏷️ Categorias",
            command=self.show_category_manager,
            height=40,
            width=130
        )
        self.btn_categorias.pack(side="left", padx=(0, 10))

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

        # ✅ NOVO BOTÃO: Robô Athos
        self.athos_button = ctk.CTkButton(
            second_row,
            text="🤖 Robô Athos",
            command=self.open_athos_window,
            height=40,
            width=130
        )
        self.athos_button.pack(side="left", padx=(0, 10))

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

        # ✅ Indicadores de disponibilidade
        self.supplier_status_var = tk.StringVar(value="")
        ctk.CTkLabel(status_frame, textvariable=self.supplier_status_var, font=ctk.CTkFont(size=12), anchor="w", text_color=("gray70", "gray50")).pack(fill="x", pady=(0, 2))

        self.categories_status_var = tk.StringVar(value="")
        ctk.CTkLabel(status_frame, textvariable=self.categories_status_var, font=ctk.CTkFont(size=12), anchor="w", text_color=("gray70", "gray50")).pack(fill="x", pady=(0, 2))

        self.athos_status_var = tk.StringVar(value="")
        ctk.CTkLabel(status_frame, textvariable=self.athos_status_var, font=ctk.CTkFont(size=12), anchor="w", text_color=("gray70", "gray50")).pack(fill="x", pady=(0, 2))

    # =========================
    # Helpers UI
    # =========================
    def create_footer(self):
        footer = ctk.CTkFrame(self.root, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkLabel(
            footer,
            text="© D'Rossi • v2.1",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray40")
        ).pack(anchor="e")

    def create_floating_color_button(self):
        """Botão flutuante (paleta de cores)"""
        try:
            self.color_palette_btn = ctk.CTkButton(
                self.root,
                text="🎨",
                width=44,
                height=44,
                corner_radius=22,
                command=self.open_color_customization,
                fg_color="#1f538d"
            )
            self.color_palette_btn.place(relx=0.95, rely=0.90, anchor="center")
        except Exception as e:
            logger.debug(f"Erro ao criar botão flutuante: {e}")

    def open_color_customization(self):
        """Abre janela de customização de cores"""
        try:
            top = ctk.CTkToplevel(self.root)
            top.title("🎨 Personalizar Cores")
            top.geometry("520x420")

            ctk.CTkLabel(top, text="Escolha uma cor base:", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 10))

            colors = ["#1f538d", "#0f7a5c", "#7a0f3a", "#7a5c0f", "#5c0f7a", "#0f5c7a", "#222222"]
            grid = ctk.CTkFrame(top, fg_color="transparent")
            grid.pack(padx=20, pady=10)

            for i, c in enumerate(colors):
                btn = ctk.CTkButton(
                    grid,
                    text=c,
                    width=140,
                    height=42,
                    fg_color=c,
                    hover_color=self._darken_color(c),
                    command=lambda cc=c: self._update_interface_colors(cc)
                )
                btn.grid(row=i // 2, column=i % 2, padx=10, pady=10, sticky="ew")

            ctk.CTkButton(top, text="🔄 Resetar", command=self.reset_colors).pack(pady=(20, 10))

        except Exception as e:
            logger.error(f"Erro ao abrir customização de cores: {e}")

    def reset_colors(self):
        try:
            if messagebox.askyesno("🔄 Resetar Cores", "Deseja resetar todas as cores para o padrão?\n\nIsso irá aplicar o tema azul padrão."):
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
            if hasattr(self, 'color_palette_btn'):
                self.color_palette_btn.configure(fg_color=color_hex)
            logger.info(f"🎨 Interface atualizada com cor: {color_hex}")
        except Exception as e:
            logger.error(f"Erro ao atualizar interface: {e}")

    def _darken_color(self, color_hex: str, factor: float = 0.8) -> str:
        """Escurece uma cor para efeito hover"""
        try:
            color_hex = color_hex.lstrip('#')
            r = int(color_hex[0:2], 16)
            g = int(color_hex[2:4], 16)
            b = int(color_hex[4:6], 16)
            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#1f538d"

    # =========================
    # Arquivos / Planilhas
    # =========================
    def guess_default_sheet(self, sheet_names: List[str]) -> Optional[str]:
        """Tenta descobrir a aba mais provável"""
        if not sheet_names:
            return None

        preferred = ["BASE", "PRODUTOS", "CADASTRO", "PLANILHA", "Sheet1"]
        for p in preferred:
            for s in sheet_names:
                if p.lower() == s.lower():
                    logger.info(f"🎯 Aba preferida encontrada: '{s}'")
                    return s

        logger.info(f"🎯 Usando primeira aba como padrão: '{sheet_names[0]}'")
        return sheet_names[0]

    def on_file_selected(self):
        """Callback quando arquivo é selecionado - auto-atualizar abas"""
        try:
            if hasattr(self, 'origin_file_var') and self.origin_file_var.get():
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
            if var == getattr(self, "origin_file_var", None):
                self.root.after(100, self.on_file_selected)

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

            from ..processors.excel_reader import ExcelReader
            reader = ExcelReader()

            logger.info(f"🔍 Buscando abas do arquivo: {origin_file_path}")
            sheet_names = reader.get_sheet_names(origin_file_path)

            if sheet_names:
                self.sheet_combobox.configure(values=sheet_names)

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
            else:
                self.sheet_combobox.configure(values=["Nenhuma aba encontrada"])
                self.sheet_combobox.set("Nenhuma aba encontrada")
                self.sheet_status_label.configure(text="❌ Nenhuma aba encontrada no arquivo.")
        except Exception as e:
            logger.error(f"Erro ao atualizar abas: {e}")
            messagebox.showerror("❌ Erro", f"Erro ao listar abas:\n{e}")

    # =========================
    # E-mail
    # =========================
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

            self.test_email_btn.configure(state="disabled", text="🔄 Testando.")
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
            self.config.enable_pricing = bool(self.enable_pricing_var.get())

            save_config(self.config)
            messagebox.showinfo("Sucesso", "✅ Configurações salvas com sucesso!")

        except Exception as e:
            messagebox.showerror("Erro", f"❌ Erro ao salvar configurações:\n{e}")

    # =========================
    # Processamento
    # =========================
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
                messagebox.showerror("Erro", "Configure o e-mail ou desative o envio de relatório")
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
                "Selecione um arquivo primeiro.",
                "Nenhuma aba encontrada",
                "Selecione uma aba."
            ]:
                self.root.after(0, lambda: messagebox.showerror("❌ Erro", "Selecione uma aba válida!"))
                return

            sheet_name = selected_sheet
            logger.info(f"📋 Aba selecionada para processamento: '{sheet_name}'")

            # Configuração da marca
            brand_name = self.brand_var.get() or "D'Rossi"
            self.config.default_brand = brand_name

            # ✅ ATUALIZAR CONFIGURAÇÃO COM OS VALORES DO PRAZO DE EXCEÇÃO
            self.config.enable_exception_prazo = self.enable_exception_prazo_var.get()
            try:
                self.config.exception_prazo_days = int(self.exception_prazo_days_var.get())
            except ValueError:
                self.config.exception_prazo_days = 0

            # Resolver fornecedor
            supplier_code, official_supplier_name = self.resolve_supplier_code(brand_name)
            logger.info(f"Fornecedor resolvido: code={supplier_code}, name='{official_supplier_name}'")

            # Atualizar status UI
            self.root.after(0, self._processing_ui_start)

            # Processar
            result = self.processor.process(
                origin_file=origin_file,
                sheet_name=sheet_name,
                supplier_code=supplier_code,
                supplier_name=official_supplier_name,
                enable_pricing=bool(self.enable_pricing_var.get()),
                cost_file=Path(self.cost_file_var.get()) if self.enable_pricing_var.get() else None,
                send_email=bool(self.send_email_var.get()),
                email_config=self.config.email if self.send_email_var.get() else None,
                on_progress=self._on_progress
            )

            self.root.after(0, lambda: self._processing_ui_finish(result))

        except Exception as e:
            logger.error(f"Erro no processamento: {e}")
            self.root.after(0, lambda: messagebox.showerror("Erro", f"Erro no processamento:\n{e}"))
        finally:
            self.processing = False
            self.root.after(0, self._processing_ui_end)

    def _processing_ui_start(self):
        try:
            self.status_var.set("⏳ Processando...")
            self.progress_var.set(0)
            self.progress_bar.pack(fill="x", pady=(5, 10))
            self.process_button.configure(state="disabled")
        except Exception:
            pass

    def _processing_ui_end(self):
        try:
            self.process_button.configure(state="normal")
            self.progress_bar.pack_forget()
            self.status_var.set("Pronto para processar")
        except Exception:
            pass

    def _on_progress(self, pct: float, msg: str = ""):
        try:
            self.progress_var.set(max(0.0, min(1.0, float(pct))))
            if msg:
                self.status_var.set(msg)
        except Exception:
            pass

    def _processing_ui_finish(self, result):
        try:
            if result and getattr(result, "success", False):
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
                errors = getattr(result, "errors", []) if result else ["Erro desconhecido"]
                error_msg = "\n".join(errors[:5])
                if len(errors) > 5:
                    error_msg += f"\n... e mais {len(errors) - 5} erros"

                messagebox.showerror("Erro no Processamento", f"❌ Falha no processamento:\n\n{error_msg}")
        except Exception as e:
            logger.error(f"Erro ao finalizar UI: {e}")

    # =========================
    # Janelas secundárias
    # =========================
    def show_logs(self):
        """Mostra logs (se houver LogViewer, usa ele; senão, placeholder)"""
        try:
            if LogViewer is None:
                messagebox.showinfo("📋 Logs", "Funcionalidade de logs em desenvolvimento")
                return

            # Reutilizar janela se existir
            if self.log_viewer and hasattr(self.log_viewer, "window") and self.log_viewer.window and self.log_viewer.window.winfo_exists():
                self.log_viewer.show()
            else:
                self.log_viewer = LogViewer(self.root, self.config.logs_dir)
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
                os.startfile(output_dir)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(output_dir)])
            else:
                subprocess.run(["xdg-open", str(output_dir)])
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")

    def show_supplier_manager(self):
        """Mostra janela de gerenciamento de fornecedores (se disponível)."""
        # Se o módulo UI não existe, já sinaliza
        if not SUPPLIER_SYSTEM_AVAILABLE or SupplierManagerWindow is None:
            messagebox.showinfo(
                "Fornecedores (indisponível)",
                "O módulo de Fornecedores não está disponível nesta instalação.\n"
                "Se você precisar dele, instale as dependências e garanta que o arquivo "
                "src/ui/components/supplier_manager.py exista."
            )
            return

        # Se o backend (sqlite/arquivo/permissão) não está ok, não abre
        try:
            available = bool(getattr(self, "supplier_db_available", False)) and bool(getattr(self.processor, "supplier_db", None))
        except Exception:
            available = False

        if not available:
            motivo = getattr(self, "supplier_status_message", "") or "Indisponível"
            messagebox.showinfo(
                "Fornecedores (indisponível)",
                "O banco de fornecedores está indisponível no momento.\n\n"
                f"Motivo: {motivo}\n\n"
                "O app continua funcionando normalmente — apenas o gerenciamento de fornecedores fica desativado."
            )
            return

        try:
            # Reusa a instância do DB já inicializada no ProductProcessor
            db = getattr(self.processor, "supplier_db", None)
            if not db:
                raise RuntimeError("supplier_db não inicializado")

            # Evitar duplicar janela
            if self.supplier_manager_window and hasattr(self.supplier_manager_window, "winfo_exists"):
                try:
                    if self.supplier_manager_window.winfo_exists():
                        self.supplier_manager_window.focus()
                        self.supplier_manager_window.lift()
                        return
                except Exception:
                    pass

            self.supplier_manager_window = SupplierManagerWindow(self.root, db)
        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de fornecedores: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o gerenciador de fornecedores:\n{e}")
        finally:
            # Atualiza status no UI, caso algo tenha mudado
            try:
                self.supplier_db_available = bool(self.processor.is_supplier_db_available())
                self.supplier_status_message = getattr(self.processor, "supplier_status_message", "") or ""
            except Exception:
                pass
            self.refresh_system_status()

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

            if self.catalog_window and hasattr(self.catalog_window, 'window') and self.catalog_window.window and self.catalog_window.window.winfo_exists():
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

            if self.costs_window and hasattr(self.costs_window, 'window') and self.costs_window.window and self.costs_window.window.winfo_exists():
                self.costs_window.show()
            else:
                self.costs_window = CostsManagerWindow(self.root)
        except Exception as e:
            logger.error(f"Erro ao abrir gerenciador de custos: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir gerenciador de custos:\n{e}")

    # =========================
    # ✅ NOVO: Robô Athos
    # =========================
    def open_athos_window(self):
        """Abre a tela Robô Athos"""
        if not ATHOS_SYSTEM_AVAILABLE or AthosWindow is None:
            messagebox.showerror(
                "Erro",
                "Tela Robô Athos não está disponível.\n"
                "Verifique se o arquivo src/ui/athos_window.py foi criado e os services athos_* existem."
            )
            return

        try:
            # Evitar duplicar janela
            if self.athos_window and hasattr(self.athos_window, "winfo_exists"):
                try:
                    if self.athos_window.winfo_exists():
                        self.athos_window.focus()
                        self.athos_window.lift()
                        return
                except Exception:
                    pass

            self.athos_window = AthosWindow(self.root)
        except Exception as e:
            logger.error(f"Erro ao abrir Robô Athos: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir Robô Athos:\n{e}")

    # =========================
    # Fornecedor
    # =========================
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

        db = getattr(getattr(self, 'processor', None), 'supplier_db', None)
        if not db or not getattr(self, 'supplier_db_available', False):
            logger.warning("Banco de fornecedores não disponível, usando código padrão")
            return 0, brand_name

        try:
            supplier = db.search_supplier_by_name(brand_name)

            if supplier:
                logger.info(f"Fornecedor encontrado: '{brand_name}' → '{supplier.name}' (código: {supplier.code})")
                return supplier.code, supplier.name
            else:
                logger.warning(f"Fornecedor não encontrado no banco: '{brand_name}' - usando código padrão (0)")
                return 0, brand_name

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor '{brand_name}': {e}")
            return 0, brand_name

    # =========================
    # Execução
    # =========================
    def run(self):
        """Executa a aplicação"""
        self.root.mainloop()


def main():
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
