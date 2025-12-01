"""Diálogo para importação de fornecedor e custos diretamente de planilha"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import logging
from typing import Optional, Dict, Any, List
import pandas as pd

from ...core.costs_database import CostsDatabase, FornecedorCustos
from ...services.costs_importer import CostsImporter

logger = logging.getLogger(__name__)


class SupplierSpreadsheetImportDialog:
    """Diálogo para importação completa de fornecedor + custos"""

    def __init__(self, parent, db: CostsDatabase):
        self.parent = parent
        self.db = db
        self.result = None
        self.file_path = None
        self.sheet_names = []
        self.detected_headers = {}

        # Variáveis do formulário
        self.supplier_name_var = tk.StringVar()
        self.supplier_code_var = tk.StringVar()
        self.file_path_var = tk.StringVar()
        self.sheet_name_var = tk.StringVar()
        self.header_row_var = tk.IntVar(value=1)

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("📥 Importar Fornecedor + Custos da Planilha")
        self.dialog.geometry("900x800")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Criar interface
        self.create_widgets()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 900) // 2
        y = (self.dialog.winfo_screenheight() - 800) // 2
        self.dialog.geometry(f"900x800+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="📥 Importar Fornecedor + Custos da Planilha",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Notebook para etapas
        self.notebook = ctk.CTkTabview(main_frame)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Etapa 1: Dados do Fornecedor
        self.notebook.add("1️⃣ Fornecedor")
        self.create_supplier_tab()

        # Etapa 2: Arquivo
        self.notebook.add("2️⃣ Arquivo")
        self.create_file_tab()

        # Etapa 3: Configuração
        self.notebook.add("3️⃣ Configuração")
        self.create_config_tab()

        # Etapa 4: Prévia
        self.notebook.add("4️⃣ Prévia")
        self.create_preview_tab()

        # Botões
        self.create_buttons(main_frame)

    def create_supplier_tab(self):
        """Cria aba de dados do fornecedor"""
        supplier_frame = self.notebook.tab("1️⃣ Fornecedor")

        # Instruções
        instructions_frame = ctk.CTkFrame(supplier_frame)
        instructions_frame.pack(fill="x", padx=20, pady=(20, 15))

        instructions_text = """📋 ETAPA 1: Dados do Fornecedor

Digite as informações básicas do fornecedor que será criado.
O fornecedor será cadastrado automaticamente no sistema junto com os custos da planilha."""

        ctk.CTkLabel(
            instructions_frame,
            text=instructions_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(padx=20, pady=20)

        # Formulário do fornecedor
        form_frame = ctk.CTkFrame(supplier_frame)
        form_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Nome do fornecedor (obrigatório)
        self.create_form_field(
            form_frame,
            "Nome do Fornecedor *",
            self.supplier_name_var,
            "Ex: NOVA MOBILIA LTDA",
            row=0
        )

        # Código do fornecedor (opcional)
        self.create_form_field(
            form_frame,
            "Código do Fornecedor",
            self.supplier_code_var,
            "Ex: 1500 (opcional - será gerado automaticamente se vazio)",
            row=1
        )

        # Informações adicionais
        info_frame = ctk.CTkFrame(supplier_frame)
        info_frame.pack(fill="x", padx=20, pady=(0, 20))

        info_text = """ℹ️ Informações Importantes:

• O nome do fornecedor será usado para identificar os produtos na planilha
• Se o código não for informado, será gerado automaticamente
• Você poderá editar outras informações do fornecedor depois da importação
• A planilha deve conter pelo menos colunas de código/nome do produto e custos"""

        ctk.CTkLabel(
            info_frame,
            text=info_text,
            font=ctk.CTkFont(size=11),
            justify="left",
            text_color=("gray60", "gray40")
        ).pack(padx=20, pady=15)

    def create_file_tab(self):
        """Cria aba de seleção de arquivo"""
        file_frame = self.notebook.tab("2️⃣ Arquivo")

        # Instruções
        instructions_frame = ctk.CTkFrame(file_frame)
        instructions_frame.pack(fill="x", padx=20, pady=(20, 15))

        instructions_text = """📁 ETAPA 2: Seleção do Arquivo

Selecione a planilha Excel (.xlsx, .xls) ou CSV que contém os custos do fornecedor.
O sistema irá detectar automaticamente as abas disponíveis e os cabeçalhos."""

        ctk.CTkLabel(
            instructions_frame,
            text=instructions_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(padx=20, pady=20)

        # Seleção de arquivo
        file_selection_frame = ctk.CTkFrame(file_frame)
        file_selection_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            file_selection_frame,
            text="📂 Arquivo da Planilha:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Frame para seleção
        file_input_frame = ctk.CTkFrame(file_selection_frame, fg_color="transparent")
        file_input_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.file_entry = ctk.CTkEntry(
            file_input_frame,
            textvariable=self.file_path_var,
            placeholder_text="Selecione a planilha com os custos...",
            state="readonly",
            height=35
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            file_input_frame,
            text="📂 Procurar",
            command=self.select_file,
            width=120,
            height=35
        ).pack(side="right")

        # Informações do arquivo
        self.file_info_frame = ctk.CTkFrame(file_frame)
        self.file_info_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.file_info_text = ctk.CTkTextbox(
            self.file_info_frame,
            height=150,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.file_info_text.pack(fill="both", expand=True, padx=20, pady=20)
        self.file_info_text.insert("1.0", "Selecione um arquivo para ver as informações...")
        self.file_info_text.configure(state="disabled")

    def create_config_tab(self):
        """Cria aba de configuração"""
        config_frame = self.notebook.tab("3️⃣ Configuração")

        # Instruções
        instructions_frame = ctk.CTkFrame(config_frame)
        instructions_frame.pack(fill="x", padx=20, pady=(20, 15))

        instructions_text = """⚙️ ETAPA 3: Configuração da Importação

Configure qual aba da planilha usar e em qual linha estão os cabeçalhos.
O sistema irá detectar automaticamente as colunas disponíveis."""

        ctk.CTkLabel(
            instructions_frame,
            text=instructions_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(padx=20, pady=20)

        # Configurações
        settings_frame = ctk.CTkFrame(config_frame)
        settings_frame.pack(fill="x", padx=20, pady=(0, 15))

        # Aba da planilha
        sheet_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        sheet_frame.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            sheet_frame,
            text="📊 Aba da Planilha:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.sheet_combo = ctk.CTkComboBox(
            sheet_frame,
            variable=self.sheet_name_var,
            values=["Selecione um arquivo primeiro"],
            state="disabled",
            width=300
        )
        self.sheet_combo.pack(side="left", padx=(0, 10))

        # Linha do cabeçalho
        header_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(10, 20))

        ctk.CTkLabel(
            header_frame,
            text="📋 Linha do Cabeçalho:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.header_spinbox = ctk.CTkEntry(
            header_frame,
            textvariable=self.header_row_var,
            width=80,
            height=30
        )
        self.header_spinbox.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            header_frame,
            text="🔍 Detectar Cabeçalhos",
            command=self.detect_headers,
            width=150,
            height=30
        ).pack(side="left", padx=(10, 0))

        # Cabeçalhos detectados
        self.headers_frame = ctk.CTkFrame(config_frame)
        self.headers_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkLabel(
            self.headers_frame,
            text="🔍 Cabeçalhos Detectados:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        self.headers_text = ctk.CTkTextbox(
            self.headers_frame,
            height=200,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.headers_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.headers_text.insert("1.0", "Configure o arquivo e clique em 'Detectar Cabeçalhos'...")
        self.headers_text.configure(state="disabled")

    def create_preview_tab(self):
        """Cria aba de prévia"""
        preview_frame = self.notebook.tab("4️⃣ Prévia")

        # Instruções
        instructions_frame = ctk.CTkFrame(preview_frame)
        instructions_frame.pack(fill="x", padx=20, pady=(20, 15))

        instructions_text = """👁️ ETAPA 4: Prévia da Importação

Visualize como os dados serão importados antes de confirmar.
Verifique se as colunas foram mapeadas corretamente."""

        ctk.CTkLabel(
            instructions_frame,
            text=instructions_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(padx=20, pady=20)

        # Botão para gerar prévia
        preview_button_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")
        preview_button_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.generate_preview_button = ctk.CTkButton(
            preview_button_frame,
            text="🔄 Gerar Prévia",
            command=self.generate_preview,
            width=150,
            height=35,
            state="disabled"
        )
        self.generate_preview_button.pack(side="left")

        # Área da prévia
        self.preview_text_frame = ctk.CTkFrame(preview_frame)
        self.preview_text_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.preview_text = ctk.CTkTextbox(
            self.preview_text_frame,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.preview_text.pack(fill="both", expand=True, padx=20, pady=20)
        self.preview_text.insert("1.0", "Configure todas as etapas anteriores e clique em 'Gerar Prévia'...")
        self.preview_text.configure(state="disabled")

    def create_form_field(self, parent, label_text, var, placeholder, row):
        """Cria um campo do formulário"""
        # Frame do campo
        field_frame = ctk.CTkFrame(parent, fg_color="transparent")
        field_frame.pack(fill="x", padx=20, pady=10)

        # Label
        label = ctk.CTkLabel(
            field_frame,
            text=label_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=200
        )
        label.pack(side="left", padx=(0, 10))

        # Entry
        entry = ctk.CTkEntry(
            field_frame,
            textvariable=var,
            placeholder_text=placeholder,
            height=35
        )
        entry.pack(side="left", fill="x", expand=True)

        return entry

    def create_buttons(self, parent):
        """Cria botões do diálogo"""
        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Cancelar
        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        # Importar
        self.import_button = ctk.CTkButton(
            buttons_frame,
            text="📥 Importar Tudo",
            command=self.start_import,
            width=150,
            height=35,
            state="disabled",
            fg_color="#2B8B3D",
            hover_color="#228B22"
        )
        self.import_button.pack(side="right")

        # Navegação entre abas
        nav_frame = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        nav_frame.pack(side="left")

        ctk.CTkButton(
            nav_frame,
            text="⬅️ Anterior",
            command=self.previous_tab,
            width=100,
            height=35
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            nav_frame,
            text="Próximo ➡️",
            command=self.next_tab,
            width=100,
            height=35
        ).pack(side="left")

    def select_file(self):
        """Seleciona arquivo da planilha"""
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha de Custos",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            self.file_path = Path(file_path)
            self.file_path_var.set(str(self.file_path))

            # Analisar arquivo
            self.analyze_file()

    def analyze_file(self):
        """Analisa o arquivo selecionado"""
        if not self.file_path:
            return

        try:
            self.file_info_text.configure(state="normal")
            self.file_info_text.delete("1.0", "end")
            self.file_info_text.insert("1.0", "🔄 Analisando arquivo...")
            self.file_info_text.configure(state="disabled")

            def analyze():
                try:
                    # Ler arquivo para obter informações
                    if self.file_path.suffix.lower() == '.csv':
                        # CSV - apenas uma "aba"
                        df = pd.read_csv(self.file_path, nrows=5)
                        self.sheet_names = ["CSV"]
                        info_text = f"""📁 INFORMAÇÕES DO ARQUIVO

📂 Arquivo: {self.file_path.name}
📊 Tipo: CSV
📋 Colunas encontradas: {len(df.columns)}
📦 Primeiras 5 linhas lidas para análise

🗂️ COLUNAS DISPONÍVEIS:
{chr(10).join(f"  • {col}" for col in df.columns)}"""

                    else:
                        # Excel - verificar abas
                        excel_file = pd.ExcelFile(self.file_path)
                        self.sheet_names = excel_file.sheet_names

                        # Ler primeira aba para análise
                        df = pd.read_excel(self.file_path, sheet_name=self.sheet_names[0], nrows=5)

                        info_text = f"""📁 INFORMAÇÕES DO ARQUIVO

📂 Arquivo: {self.file_path.name}
📊 Tipo: Excel
📑 Abas disponíveis: {len(self.sheet_names)}
📋 Colunas na primeira aba: {len(df.columns)}
📦 Primeiras 5 linhas lidas para análise

📑 ABAS ENCONTRADAS:
{chr(10).join(f"  • {sheet}" for sheet in self.sheet_names)}

🗂️ COLUNAS NA ABA '{self.sheet_names[0]}':
{chr(10).join(f"  • {col}" for col in df.columns)}"""

                    # Atualizar interface
                    self.dialog.after(0, lambda: self.update_file_info(info_text))

                except Exception as e:
                    error_text = f"❌ Erro ao analisar arquivo: {str(e)}"
                    self.dialog.after(0, lambda: self.update_file_info(error_text))

            thread = threading.Thread(target=analyze, daemon=True)
            thread.start()

        except Exception as e:
            self.update_file_info(f"❌ Erro: {str(e)}")

    def update_file_info(self, info_text):
        """Atualiza informações do arquivo"""
        self.file_info_text.configure(state="normal")
        self.file_info_text.delete("1.0", "end")
        self.file_info_text.insert("1.0", info_text)
        self.file_info_text.configure(state="disabled")

        # Atualizar combo de abas
        if self.sheet_names:
            self.sheet_combo.configure(values=self.sheet_names, state="normal")
            self.sheet_combo.set(self.sheet_names[0])
            self.sheet_name_var.set(self.sheet_names[0])

            # Habilitar botão de detectar cabeçalhos
            self.generate_preview_button.configure(state="normal")

    def detect_headers(self):
        """Detecta cabeçalhos da planilha"""
        if not self.file_path:
            messagebox.showwarning("Aviso", "Selecione um arquivo primeiro")
            return

        try:
            self.headers_text.configure(state="normal")
            self.headers_text.delete("1.0", "end")
            self.headers_text.insert("1.0", "�� Detectando cabeçalhos...")
            self.headers_text.configure(state="disabled")

            def detect():
                try:
                    header_row = self.header_row_var.get()
                    sheet_name = self.sheet_name_var.get() if self.sheet_name_var.get() != "CSV" else None

                    # Ler cabeçalhos
                    if self.file_path.suffix.lower() == '.csv':
                        df = pd.read_csv(self.file_path, header=header_row - 1, nrows=0)
                    else:
                        df = pd.read_excel(self.file_path, sheet_name=sheet_name, header=header_row - 1, nrows=0)

                    headers = list(df.columns)

                    # Mapear automaticamente
                    importer = CostsImporter(self.db)
                    mapped_columns = importer._auto_map_columns(headers)

                    headers_text = f"""🔍 CABEÇALHOS DETECTADOS

📋 Linha do cabeçalho: {header_row}
�� Total de colunas: {len(headers)}
✅ Colunas mapeadas: {len(mapped_columns)}

🗂️ TODAS AS COLUNAS ENCONTRADAS:
{chr(10).join(f"  {i + 1:2d}. {col}" for i, col in enumerate(headers))}

✅ MAPEAMENTO AUTOMÁTICO:
{chr(10).join(f"  • {field}: {col}" for field, col in mapped_columns.items()) if mapped_columns else "  Nenhuma coluna foi mapeada automaticamente"}

ℹ️ O sistema tentará mapear automaticamente as colunas baseado nos nomes.
   Colunas não mapeadas serão ignoradas durante a importação."""

                    self.detected_headers = {
                        'headers': headers,
                        'mapped': mapped_columns,
                        'header_row': header_row,
                        'sheet_name': sheet_name
                    }

                    self.dialog.after(0, lambda: self.update_headers_info(headers_text))

                except Exception as e:
                    error_text = f"❌ Erro ao detectar cabeçalhos: {str(e)}"
                    self.dialog.after(0, lambda: self.update_headers_info(error_text))

            thread = threading.Thread(target=detect, daemon=True)
            thread.start()

        except Exception as e:
            self.update_headers_info(f"❌ Erro: {str(e)}")

    def update_headers_info(self, headers_text):
        """Atualiza informações dos cabeçalhos"""
        self.headers_text.configure(state="normal")
        self.headers_text.delete("1.0", "end")
        self.headers_text.insert("1.0", headers_text)
        self.headers_text.configure(state="disabled")

    def generate_preview(self):
        """Gera prévia da importação"""
        if not self.validate_form():
            return

        try:
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", "🔄 Gerando prévia...")
            self.preview_text.configure(state="disabled")

            def generate():
                try:
                    supplier_name = self.supplier_name_var.get().strip()
                    supplier_code = self.supplier_code_var.get().strip()

                    # Gerar prévia usando o importador
                    importer = CostsImporter(self.db)

                    header_row = self.header_row_var.get()
                    sheet_name = self.sheet_name_var.get() if self.sheet_name_var.get() != "CSV" else None

                    preview = importer.get_import_preview(
                        self.file_path,
                        header_row=header_row,
                        sheet_name=sheet_name
                    )

                    if "error" in preview:
                        preview_text = f"❌ Erro na prévia: {preview['error']}"
                    else:
                        preview_text = f"""👁️ PRÉVIA DA IMPORTAÇÃO COMPLETA

🏢 FORNECEDOR QUE SERÁ CRIADO:
  • Nome: {supplier_name}
  • Código: {supplier_code or 'Será gerado automaticamente'}

📁 ARQUIVO:
  • Arquivo: {self.file_path.name}
  • Aba: {sheet_name or 'CSV'}
  • Linha do cabeçalho: {header_row}

📊 DADOS DA PLANILHA:
  • Total de linhas: {preview['total_rows']}
  • Produtos estimados: {preview['estimated_products']}
  • Colunas encontradas: {len(preview['columns_found'])}
  • Colunas mapeadas: {len(preview['columns_mapped'])}

✅ MAPEAMENTO DE COLUNAS:
{chr(10).join(f"  • {field}: {col}" for field, col in preview['columns_mapped'].items())}

📋 AMOSTRA DOS PRIMEIROS PRODUTOS:"""

                        if preview['sample_data']:
                            for sample in preview['sample_data']:
                                preview_text += f"""
  Linha {sample['linha']}:
    • Código: {sample.get('codigo', 'N/A')}
    • Nome: {sample.get('nome', 'N/A')}
    • Custo: {sample.get('custo_unitario', 'N/A')}"""
                        else:
                            preview_text += "\n  Nenhum produto válido encontrado"

                        preview_text += f"""

🚀 AÇÕES QUE SERÃO EXECUTADAS:
  1. Criar fornecedor '{supplier_name}' no banco de dados
  2. Importar {preview['estimated_products']} produtos com custos
  3. Mapear automaticamente as colunas identificadas
  4. Calcular campos derivados (custo total, markup, etc.)

⚠️ IMPORTANTE: Esta operação criará um novo fornecedor e importará todos os dados.
   Certifique-se de que os dados estão corretos antes de prosseguir."""

                    self.dialog.after(0, lambda: self.update_preview(preview_text,
                                                                     preview.get('estimated_products', 0) > 0))

                except Exception as e:
                    error_text = f"❌ Erro ao gerar prévia: {str(e)}"
                    self.dialog.after(0, lambda: self.update_preview(error_text, False))

            thread = threading.Thread(target=generate, daemon=True)
            thread.start()

        except Exception as e:
            self.update_preview(f"❌ Erro: {str(e)}", False)

    def update_preview(self, preview_text, can_import):
        """Atualiza prévia"""
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", preview_text)
        self.preview_text.configure(state="disabled")

        # Habilitar/desabilitar botão de importação
        if can_import:
            self.import_button.configure(state="normal")
        else:
            self.import_button.configure(state="disabled")

    def validate_form(self):
        """Valida formulário"""
        if not self.supplier_name_var.get().strip():
            messagebox.showerror("Erro", "Nome do fornecedor é obrigatório")
            self.notebook.set("1️⃣ Fornecedor")
            return False

        if not self.file_path:
            messagebox.showerror("Erro", "Selecione um arquivo")
            self.notebook.set("2️⃣ Arquivo")
            return False

        if not self.detected_headers:
            messagebox.showerror("Erro", "Detecte os cabeçalhos primeiro")
            self.notebook.set("3️⃣ Configuração")
            return False

        return True

    def start_import(self):
        """Inicia importação completa"""
        if not self.validate_form():
            return

        supplier_name = self.supplier_name_var.get().strip()
        supplier_code = self.supplier_code_var.get().strip()

        # Confirmar importação
        response = messagebox.askyesno(
            "Confirmar Importação Completa",
            f"Confirma a criação do fornecedor e importação dos custos?\n\n"
            f"🏢 Fornecedor: {supplier_name}\n"
            f"📁 Arquivo: {self.file_path.name}\n"
            f"📊 Produtos estimados: {self.detected_headers.get('estimated_products', 'N/A')}\n\n"
            f"Esta operação pode demorar alguns minutos."
        )

        if not response:
            return

        # Executar importação
        self.execute_import()

    def execute_import(self):
        """Executa a importação completa"""
        # Criar diálogo de progresso
        self.create_progress_dialog()

        def run_import():
            try:
                supplier_name = self.supplier_name_var.get().strip()
                supplier_code = self.supplier_code_var.get().strip()

                # Etapa 1: Criar fornecedor
                self.update_status("🏢 Criando fornecedor...")

                # Gerar código se não informado
                if not supplier_code:
                    # Buscar maior código existente
                    existing_suppliers = self.db.list_fornecedores()
                    max_code = 0
                    for supplier in existing_suppliers:
                        try:
                            code = int(supplier.codigo)
                            max_code = max(max_code, code)
                        except:
                            continue
                    supplier_code = str(max_code + 1)

                # Criar fornecedor
                fornecedor = FornecedorCustos(
                    nome=supplier_name,
                    codigo=supplier_code,
                    linha_cabecalho=self.header_row_var.get(),
                    estrutura_planilha="{}",
                    colunas_mapeamento="{}"
                )

                fornecedor_id = self.db.add_fornecedor(fornecedor)
                if not fornecedor_id:
                    raise Exception("Falha ao criar fornecedor")

                self.update_progress(25)

                # Etapa 2: Importar custos
                self.update_status(f"📥 Importando custos para {supplier_name}...")

                importer = CostsImporter(self.db)

                header_row = self.header_row_var.get()
                sheet_name = self.sheet_name_var.get() if self.sheet_name_var.get() != "CSV" else None

                result = importer.import_from_excel(
                    self.file_path,
                    supplier_name,
                    header_row=header_row,
                    sheet_name=sheet_name,
                    update_existing=False,
                    progress_callback=lambda p: self.update_progress(25 + (p * 0.75)),
                    status_callback=self.update_status
                )

                # Finalizar
                self.dialog.after(0, lambda: self.import_completed(result, supplier_name))

            except Exception as e:
                error_msg = f"Erro na importação completa: {str(e)}"
                logger.error(error_msg)
                self.dialog.after(0, lambda: self.import_error(error_msg))

        thread = threading.Thread(target=run_import, daemon=True)
        thread.start()

    def create_progress_dialog(self):
        """Cria diálogo de progresso"""
        self.progress_dialog = ctk.CTkToplevel(self.dialog)
        self.progress_dialog.title("📥 Importando Fornecedor + Custos")
        self.progress_dialog.geometry("500x200")
        self.progress_dialog.transient(self.dialog)
        self.progress_dialog.grab_set()

        # Centralizar
        self.progress_dialog.update_idletasks()
        x = (self.progress_dialog.winfo_screenwidth() - 500) // 2
        y = (self.progress_dialog.winfo_screenheight() - 200) // 2
        self.progress_dialog.geometry(f"500x200+{x}+{y}")

        frame = ctk.CTkFrame(self.progress_dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Status
        self.status_var = tk.StringVar(value="Iniciando importação completa...")
        status_label = ctk.CTkLabel(
            frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=14)
        )
        status_label.pack(pady=20)

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(
            frame,
            variable=self.progress_var,
            height=20
        )
        self.progress_bar.pack(fill="x", padx=20, pady=20)

    def update_progress(self, value: float):
        """Atualiza progresso"""
        try:
            if hasattr(self, 'progress_var'):
                self.dialog.after(0, lambda: self.progress_var.set(value / 100))
        except:
            pass

    def update_status(self, message: str):
        """Atualiza status"""
        try:
            if hasattr(self, 'status_var'):
                self.dialog.after(0, lambda: self.status_var.set(message))
        except:
            pass

    def import_completed(self, result, supplier_name):
        """Callback quando importação é concluída"""
        try:
            # Fechar diálogo de progresso
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.destroy()

            if result.success:
                message = (
                    f"🎉 Importação completa realizada com sucesso!\n\n"
                    f"🏢 Fornecedor criado: {supplier_name}\n"
                    f"📦 Produtos importados: {result.total_produtos}\n"
                    f"➕ Produtos novos: {result.produtos_novos}\n"
                    f"⏱️ Tempo total: {result.processing_time:.2f}s\n\n"
                    f"O fornecedor e todos os custos foram adicionados ao sistema."
                )

                messagebox.showinfo("Sucesso", message)
                self.result = "success"
                self.dialog.destroy()
            else:
                error_msg = (
                    f"❌ Falha na importação!\n\n"
                    f"🏢 Fornecedor: {supplier_name}\n"
                    f"⏱️ Tempo: {result.processing_time:.2f}s\n\n"
                    f"Erros: {chr(10).join(result.errors[:3])}"
                )
                messagebox.showerror("Erro", error_msg)

        except Exception as e:
            logger.error(f"Erro ao finalizar importação: {e}")

    def import_error(self, error_msg: str):
        """Callback quando há erro na importação"""
        try:
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.destroy()
            messagebox.showerror("Erro", error_msg)
        except Exception as e:
            logger.error(f"Erro ao tratar erro de importação: {e}")

    def previous_tab(self):
        """Vai para aba anterior"""
        current = self.notebook.get()
        tabs = ["1️⃣ Fornecedor", "2️⃣ Arquivo", "3️⃣ Configuração", "4️⃣ Prévia"]

        try:
            current_index = tabs.index(current)
            if current_index > 0:
                self.notebook.set(tabs[current_index - 1])
        except:
            pass

    def next_tab(self):
        """Vai para próxima aba"""
        current = self.notebook.get()
        tabs = ["1️⃣ Fornecedor", "2️⃣ Arquivo", "3️⃣ Configuração", "4️⃣ Prévia"]

        try:
            current_index = tabs.index(current)
            if current_index < len(tabs) - 1:
                self.notebook.set(tabs[current_index + 1])
        except:
            pass

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()