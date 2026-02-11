"""Interface para gerenciamento de produtos e componentes"""
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from pathlib import Path
import logging

from ...core.product_database import ProductDatabase

logger = logging.getLogger(__name__)


class ProductManagerWindow:
    """Janela de gerenciamento de produtos"""

    def __init__(self, parent, db_path: Path):
        self.parent = parent
        self.db_path = db_path
        self.db = ProductDatabase(db_path)
        self.window = None

        # Variáveis de controle
        self.selected_produto = None
        self.produtos_data = []
        self.assentos_data = []
        self.pes_bases_data = []

        self.setup_window()
        self.create_widgets()
        self.load_data()

    def setup_window(self):
        """Configura a janela principal"""
        # ✅ CORREÇÃO DO ERRO DE SCALING - ADICIONAR ESTAS LINHAS
        try:
            import customtkinter as ctk
            # Forçar scaling padrão para evitar divisão por zero
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)

            # Verificar se scaling está correto
            try:
                current_scaling = ctk.ScalingTracker.get_window_scaling()
                if current_scaling == 0 or current_scaling is None:
                    ctk.set_window_scaling(1.0)
            except Exception:
                ctk.set_window_scaling(1.0)
        except Exception as e:
            logger.warning(f"Erro ao configurar scaling: {e}")

        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("🛋️ Gerenciador de Produtos e Componentes")
        self.window.geometry("1400x900")
        self.window.minsize(1200, 800)

        # Centralizar janela
        self.window.transient(self.parent)
        self.window.grab_set()

        # Forçar janela para frente
        self.window.lift()
        self.window.focus_force()

        # Protocolo de fechamento
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="🛋️ Gerenciador de Produtos e Componentes",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Frame de conteúdo com abas
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Aba 1: Produtos
        self.create_produtos_tab()

        # Aba 2: Componentes
        self.create_componentes_tab()

        # Aba 3: Combinações
        self.create_combinacoes_tab()

        # Aba 4: Busca por EAN
        self.create_busca_tab()

        # Frame de botões inferiores
        self.create_bottom_buttons(main_frame)

    def create_produtos_tab(self):
        """Cria aba de produtos"""
        produtos_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(produtos_frame, text="📦 Produtos")

        # Título da seção
        section_title = ctk.CTkLabel(
            produtos_frame,
            text="📦 Produtos Principais (Abas da Planilha)",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        section_title.pack(pady=(20, 15))

        # Frame de controles
        controls_frame = ctk.CTkFrame(produtos_frame)
        controls_frame.pack(fill="x", padx=20, pady=(0, 15))

        # Botões de ação
        buttons_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(
            buttons_frame,
            text="➕ Adicionar Produto",
            command=self.add_produto_dialog,
            height=35,
            width=150
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            buttons_frame,
            text="✏️ Editar",
            command=self.edit_produto_dialog,
            height=35,
            width=120
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            buttons_frame,
            text="🗑️ Excluir",
            command=self.delete_produto,
            height=35,
            width=120
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            buttons_frame,
            text="🔄 Atualizar",
            command=self.load_produtos,
            height=35,
            width=120
        ).pack(side="left")

        # Lista de produtos
        list_frame = ctk.CTkFrame(produtos_frame)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Treeview para produtos
        columns = ("ID", "Nome da Aba", "Status", "Criado em")
        self.produtos_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)

        # Configurar colunas
        self.produtos_tree.heading("ID", text="ID")
        self.produtos_tree.heading("Nome da Aba", text="Nome da Aba")
        self.produtos_tree.heading("Status", text="Status")
        self.produtos_tree.heading("Criado em", text="Criado em")

        self.produtos_tree.column("ID", width=80, anchor="center")
        self.produtos_tree.column("Nome da Aba", width=300, anchor="w")
        self.produtos_tree.column("Status", width=100, anchor="center")
        self.produtos_tree.column("Criado em", width=150, anchor="center")

        # Scrollbar
        produtos_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.produtos_tree.yview)
        self.produtos_tree.configure(yscrollcommand=produtos_scrollbar.set)

        # Pack treeview e scrollbar
        self.produtos_tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        produtos_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)

        # Bind de seleção
        self.produtos_tree.bind("<<TreeviewSelect>>", self.on_produto_select)

    def create_componentes_tab(self):
        """Cria aba de componentes (assentos e pés/bases)"""
        componentes_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(componentes_frame, text="🪑 Componentes")

        # Frame principal dividido
        main_comp_frame = ctk.CTkFrame(componentes_frame, fg_color="transparent")
        main_comp_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Seletor de produto
        produto_frame = ctk.CTkFrame(main_comp_frame)
        produto_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            produto_frame,
            text="Selecione um produto para ver seus componentes:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.produto_combo_var = tk.StringVar()
        self.produto_combo = ctk.CTkComboBox(
            produto_frame,
            variable=self.produto_combo_var,
            command=self.on_produto_combo_change,
            width=300
        )
        self.produto_combo.pack(pady=(0, 15))

        # Frame dividido: Assentos | Pés/Bases
        content_frame = ctk.CTkFrame(main_comp_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)

        # Lado esquerdo: Assentos
        assentos_frame = ctk.CTkFrame(content_frame)
        assentos_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(
            assentos_frame,
            text="🪑 Assentos",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        # Botões assentos
        assentos_btn_frame = ctk.CTkFrame(assentos_frame, fg_color="transparent")
        assentos_btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            assentos_btn_frame,
            text="➕ Adicionar",
            command=self.add_assento_dialog,
            height=30,
            width=100
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            assentos_btn_frame,
            text="✏️ Editar",
            command=self.edit_assento_dialog,
            height=30,
            width=80
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            assentos_btn_frame,
            text="🗑️ Excluir",
            command=self.delete_assento,
            height=30,
            width=80
        ).pack(side="left")

        # Lista de assentos
        assentos_list_frame = ctk.CTkFrame(assentos_frame)
        assentos_list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        assentos_columns = ("ID", "Modelo", "Revestimento", "EAN")
        self.assentos_tree = ttk.Treeview(assentos_list_frame, columns=assentos_columns, show="headings", height=12)

        self.assentos_tree.heading("ID", text="ID")
        self.assentos_tree.heading("Modelo", text="Modelo")
        self.assentos_tree.heading("Revestimento", text="Revestimento")
        self.assentos_tree.heading("EAN", text="EAN")

        self.assentos_tree.column("ID", width=50, anchor="center")
        self.assentos_tree.column("Modelo", width=120, anchor="w")
        self.assentos_tree.column("Revestimento", width=150, anchor="w")
        self.assentos_tree.column("EAN", width=120, anchor="w")

        assentos_scrollbar = ttk.Scrollbar(assentos_list_frame, orient="vertical", command=self.assentos_tree.yview)
        self.assentos_tree.configure(yscrollcommand=assentos_scrollbar.set)

        self.assentos_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        assentos_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)

        # Lado direito: Pés/Bases
        pes_frame = ctk.CTkFrame(content_frame)
        pes_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

        ctk.CTkLabel(
            pes_frame,
            text="🦵 Pés/Bases",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        # Botões pés/bases
        pes_btn_frame = ctk.CTkFrame(pes_frame, fg_color="transparent")
        pes_btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            pes_btn_frame,
            text="➕ Adicionar",
            command=self.add_pe_base_dialog,
            height=30,
            width=100
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            pes_btn_frame,
            text="✏️ Editar",
            command=self.edit_pe_base_dialog,
            height=30,
            width=80
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            pes_btn_frame,
            text="🗑️ Excluir",
            command=self.delete_pe_base,
            height=30,
            width=80
        ).pack(side="left")

        # Lista de pés/bases
        pes_list_frame = ctk.CTkFrame(pes_frame)
        pes_list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        pes_columns = ("ID", "Nome", "EAN", "Qtd")
        self.pes_tree = ttk.Treeview(pes_list_frame, columns=pes_columns, show="headings", height=12)

        self.pes_tree.heading("ID", text="ID")
        self.pes_tree.heading("Nome", text="Nome")
        self.pes_tree.heading("EAN", text="EAN")
        self.pes_tree.heading("Qtd", text="Qtd")

        self.pes_tree.column("ID", width=50, anchor="center")
        self.pes_tree.column("Nome", width=180, anchor="w")
        self.pes_tree.column("EAN", width=120, anchor="w")
        self.pes_tree.column("Qtd", width=50, anchor="center")

        pes_scrollbar = ttk.Scrollbar(pes_list_frame, orient="vertical", command=self.pes_tree.yview)
        self.pes_tree.configure(yscrollcommand=pes_scrollbar.set)

        self.pes_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        pes_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)

    def create_combinacoes_tab(self):
        """Cria aba de combinações"""
        combinacoes_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(combinacoes_frame, text="🔗 Combinações")

        # Título
        title_label = ctk.CTkLabel(
            combinacoes_frame,
            text="🔗 Combinações Assento + Pé/Base",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 15))

        # Seletor de produto
        produto_comb_frame = ctk.CTkFrame(combinacoes_frame)
        produto_comb_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            produto_comb_frame,
            text="Produto:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(15, 10), pady=15)

        self.produto_comb_var = tk.StringVar()
        self.produto_comb_combo = ctk.CTkComboBox(
            produto_comb_frame,
            variable=self.produto_comb_var,
            command=self.on_produto_comb_change,
            width=300
        )
        self.produto_comb_combo.pack(side="left", padx=(0, 10), pady=15)

        ctk.CTkButton(
            produto_comb_frame,
            text="➕ Nova Combinação",
            command=self.add_combinacao,
            height=35,
            width=160
        ).pack(side="left", padx=(10, 10), pady=15)

        ctk.CTkButton(
            produto_comb_frame,
            text="🔄 Gerar Todas as Combinações",
            command=self.generate_all_combinations,
            height=35,
            width=200
        ).pack(side="left", padx=(20, 15), pady=15)

        ctk.CTkButton(
            produto_comb_frame,
            text="🗑️ Limpar Combinações",
            command=self.clear_combinations,
            height=35,
            width=180
        ).pack(side="left", padx=(10, 15), pady=15)

        # Lista de combinações
        comb_list_frame = ctk.CTkFrame(combinacoes_frame)
        comb_list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        comb_columns = ("ID", "Modelo", "Revestimento", "EAN Assento", "Pé/Base", "EAN Pé", "Qtd")
        self.combinacoes_tree = ttk.Treeview(comb_list_frame, columns=comb_columns, show="headings", height=15)

        for col in comb_columns:
            self.combinacoes_tree.heading(col, text=col)

        self.combinacoes_tree.column("ID", width=50, anchor="center")
        self.combinacoes_tree.column("Modelo", width=120, anchor="w")
        self.combinacoes_tree.column("Revestimento", width=150, anchor="w")
        self.combinacoes_tree.column("EAN Assento", width=120, anchor="w")
        self.combinacoes_tree.column("Pé/Base", width=150, anchor="w")
        self.combinacoes_tree.column("EAN Pé", width=120, anchor="w")
        self.combinacoes_tree.column("Qtd", width=50, anchor="center")

        comb_scrollbar = ttk.Scrollbar(comb_list_frame, orient="vertical", command=self.combinacoes_tree.yview)
        self.combinacoes_tree.configure(yscrollcommand=comb_scrollbar.set)

        self.combinacoes_tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        comb_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)

    def create_busca_tab(self):
        """Cria aba de busca por EAN"""
        busca_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(busca_frame, text="🔍 Busca EAN")

        # Título
        title_label = ctk.CTkLabel(
            busca_frame,
            text="🔍 Busca por Código EAN",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(30, 20))

        # Campo de busca
        search_frame = ctk.CTkFrame(busca_frame)
        search_frame.pack(fill="x", padx=50, pady=(0, 30))

        ctk.CTkLabel(
            search_frame,
            text="Digite o código EAN:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(20, 10))

        search_input_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_input_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.search_ean_var = tk.StringVar()
        self.search_ean_entry = ctk.CTkEntry(
            search_input_frame,
            textvariable=self.search_ean_var,
            placeholder_text="Digite o código EAN...",
            font=ctk.CTkFont(size=14),
            height=40
        )
        self.search_ean_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            search_input_frame,
            text="🔍 Buscar",
            command=self.search_by_ean,
            height=40,
            width=120
        ).pack(side="right")

        # Resultado da busca
        self.result_frame = ctk.CTkFrame(busca_frame)
        self.result_frame.pack(fill="both", expand=True, padx=50, pady=(0, 30))

        self.result_label = ctk.CTkLabel(
            self.result_frame,
            text="Digite um código EAN para buscar...",
            font=ctk.CTkFont(size=14),
            wraplength=600
        )
        self.result_label.pack(expand=True, pady=50)

        # Bind Enter key
        self.search_ean_entry.bind("<Return>", lambda e: self.search_by_ean())

    def create_bottom_buttons(self, parent):
        """Cria botões inferiores"""
        bottom_frame = ctk.CTkFrame(parent)
        bottom_frame.pack(fill="x", padx=20, pady=(0, 20))

        buttons_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        buttons_frame.pack(expand=True, pady=15)

        # Estatísticas
        stats = self.db.get_stats()
        stats_text = (f"📊 Produtos: {stats.get('total_produtos', 0)} | "
                      f"Assentos: {stats.get('total_assentos', 0)} | "
                      f"Pés/Bases: {stats.get('total_pes_bases', 0)} | "
                      f"Combinações: {stats.get('total_combinacoes', 0)}")

        self.stats_label = ctk.CTkLabel(
            buttons_frame,
            text=stats_text,
            font=ctk.CTkFont(size=12)
        )
        self.stats_label.pack(side="left", padx=(0, 20))

        ctk.CTkButton(
            buttons_frame,
            text="📊 Atualizar Stats",
            command=self.update_stats,
            height=35,
            width=130
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="📥 Importar Planilha",
            command=self.import_spreadsheet,
            height=35,
            width=150
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Fechar",
            command=self.on_closing,
            height=35,
            width=100
        ).pack(side="right")

    # MÉTODOS DE DADOS
    def load_data(self):
        """Carrega todos os dados"""
        self.load_produtos()
        self.update_produto_combos()
        self.update_stats()

    def load_produtos(self):
        """Carrega lista de produtos"""
        try:
            self.produtos_data = self.db.list_produtos()

            # Limpar treeview
            for item in self.produtos_tree.get_children():
                self.produtos_tree.delete(item)

            # Adicionar produtos
            for produto in self.produtos_data:
                created_at = produto.created_at.strftime("%d/%m/%Y") if produto.created_at else ""
                self.produtos_tree.insert("", "end", values=(
                    produto.id,
                    produto.nome_aba,
                    produto.status,
                    created_at
                ))

        except Exception as e:
            logger.error(f"Erro ao carregar produtos: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar produtos:\n{e}")

    def update_produto_combos(self):
        """Atualiza comboboxes de produtos"""
        try:
            produtos = [p.nome_aba for p in self.produtos_data]

            self.produto_combo.configure(values=produtos)
            self.produto_comb_combo.configure(values=produtos)

            if produtos:
                self.produto_combo.set("")
                self.produto_comb_combo.set("")

        except Exception as e:
            logger.error(f"Erro ao atualizar combos: {e}")

    def update_stats(self):
        """Atualiza estatísticas"""
        try:
            stats = self.db.get_stats()
            stats_text = (f"�� Produtos: {stats.get('total_produtos', 0)} | "
                          f"Assentos: {stats.get('total_assentos', 0)} | "
                          f"Pés/Bases: {stats.get('total_pes_bases', 0)} | "
                          f"Combinações: {stats.get('total_combinacoes', 0)}")

            self.stats_label.configure(text=stats_text)

        except Exception as e:
            logger.error(f"Erro ao atualizar stats: {e}")

    # EVENTOS
    def on_produto_select(self, event):
        """Evento de seleção de produto"""
        selection = self.produtos_tree.selection()
        if selection:
            item = self.produtos_tree.item(selection[0])
            produto_id = item['values'][0]
            self.selected_produto = next((p for p in self.produtos_data if p.id == produto_id), None)

    def on_produto_combo_change(self, value):
        """Evento de mudança no combo de produtos (componentes)"""
        if value:
            produto = next((p for p in self.produtos_data if p.nome_aba == value), None)
            if produto:
                self.load_componentes(produto.id)

    def on_produto_comb_change(self, value):
        """Evento de mudança no combo de produtos (combinações)"""
        if value:
            produto = next((p for p in self.produtos_data if p.nome_aba == value), None)
            if produto:
                self.load_combinacoes(produto.id)

    def load_componentes(self, produto_id: int):
        """Carrega componentes de um produto"""
        try:
            # Carregar assentos
            assentos = self.db.list_assentos_by_produto(produto_id)

            # Limpar treeview assentos
            for item in self.assentos_tree.get_children():
                self.assentos_tree.delete(item)

            # Adicionar assentos
            for assento in assentos:
                self.assentos_tree.insert("", "end", values=(
                    assento.id,
                    assento.modelo,
                    assento.revestimento,
                    assento.ean
                ))

            # Carregar pés/bases
            pes_bases = self.db.list_pes_bases_by_produto(produto_id)

            # Limpar treeview pés
            for item in self.pes_tree.get_children():
                self.pes_tree.delete(item)

            # Adicionar pés/bases
            for pe_base in pes_bases:
                self.pes_tree.insert("", "end", values=(
                    pe_base.id,
                    pe_base.nome,
                    pe_base.ean,
                    pe_base.quantidade
                ))

        except Exception as e:
            logger.error(f"Erro ao carregar componentes: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar componentes:\n{e}")

    def load_combinacoes(self, produto_id: int):
        """Carrega combinações de um produto"""
        try:
            combinacoes = self.db.get_combinacoes_by_produto(produto_id)

            # Limpar treeview
            for item in self.combinacoes_tree.get_children():
                self.combinacoes_tree.delete(item)

            # Adicionar combinações
            for comb in combinacoes:
                self.combinacoes_tree.insert("", "end", values=comb)

        except Exception as e:
            logger.error(f"Erro ao carregar combinações: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar combinações:\n{e}")

    # DIÁLOGOS (continuarei na próxima parte...)
    # ✅ SUBSTITUIR ESTES MÉTODOS NA CLASSE ProductManagerWindow

    def add_produto_dialog(self):
        """Diálogo para adicionar produto"""
        from .product_dialogs import ProductEditDialog

        dialog = ProductEditDialog(self.window, "Novo Produto")
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.add_produto(dialog.result["nome_aba"])
                self.load_data()
                messagebox.showinfo("Sucesso", "Produto adicionado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao adicionar produto: {e}")
                messagebox.showerror("Erro", f"Erro ao adicionar produto:\n{e}")

    def edit_produto_dialog(self):
        """Diálogo para editar produto"""
        if not self.selected_produto:
            messagebox.showwarning("Aviso", "Selecione um produto para editar")
            return

        from .product_dialogs import ProductEditDialog

        produto_data = {
            "nome_aba": self.selected_produto.nome_aba,
            "status": self.selected_produto.status
        }

        dialog = ProductEditDialog(self.window, "Editar Produto", produto_data)
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.update_produto(
                    self.selected_produto.id,
                    dialog.result["nome_aba"],
                    dialog.result["status"]
                )
                self.load_data()
                messagebox.showinfo("Sucesso", "Produto atualizado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao atualizar produto: {e}")
                messagebox.showerror("Erro", f"Erro ao atualizar produto:\n{e}")

    def delete_produto(self):
        """Exclui produto selecionado"""
        if not self.selected_produto:
            messagebox.showwarning("Aviso", "Selecione um produto para excluir")
            return

        # Confirmar exclusão
        response = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o produto '{self.selected_produto.nome_aba}'?\n\n"
            "⚠️ ATENÇÃO: Isto também excluirá:\n"
            "• Todos os assentos do produto\n"
            "• Todos os pés/bases do produto\n"
            "• Todas as combinações do produto\n\n"
            "Esta ação não pode ser desfeita!"
        )

        if response:
            try:
                self.db.delete_produto(self.selected_produto.id)
                self.selected_produto = None
                self.load_data()
                messagebox.showinfo("Sucesso", "Produto excluído com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao excluir produto: {e}")
                messagebox.showerror("Erro", f"Erro ao excluir produto:\n{e}")

    def add_assento_dialog(self):
        """Diálogo para adicionar assento"""
        produto_nome = self.produto_combo_var.get()
        if not produto_nome:
            messagebox.showwarning("Aviso", "Selecione um produto primeiro")
            return

        produto = next((p for p in self.produtos_data if p.nome_aba == produto_nome), None)
        if not produto:
            messagebox.showerror("Erro", "Produto não encontrado")
            return

        from .product_dialogs import AssentoEditDialog

        dialog = AssentoEditDialog(self.window, "Novo Assento")
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.add_assento(
                    produto_id=produto.id,
                    nome=dialog.result["nome"],
                    modelo=dialog.result["modelo"],
                    revestimento=dialog.result["revestimento"],
                    ean=dialog.result["ean"],
                    codigo=dialog.result["codigo"]
                )
                self.load_componentes(produto.id)
                self.update_stats()
                messagebox.showinfo("Sucesso", "Assento adicionado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao adicionar assento: {e}")
                messagebox.showerror("Erro", f"Erro ao adicionar assento:\n{e}")

    def edit_assento_dialog(self):
        """Diálogo para editar assento"""
        selection = self.assentos_tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um assento para editar")
            return

        # Pegar dados do assento selecionado
        item = self.assentos_tree.item(selection[0])
        assento_id = item['values'][0]

        # Buscar dados completos do assento
        assento = self.db.get_assento_by_id(assento_id)
        if not assento:
            messagebox.showerror("Erro", "Assento não encontrado")
            return

        from .product_dialogs import AssentoEditDialog

        assento_data = {
            "nome": assento.nome,
            "modelo": assento.modelo,
            "revestimento": assento.revestimento,
            "ean": assento.ean,
            "codigo": assento.codigo,
            "status": assento.status
        }

        dialog = AssentoEditDialog(self.window, "Editar Assento", assento_data)
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.update_assento(
                    assento_id=assento.id,
                    nome=dialog.result["nome"],
                    modelo=dialog.result["modelo"],
                    revestimento=dialog.result["revestimento"],
                    ean=dialog.result["ean"],
                    codigo=dialog.result["codigo"],
                    status=dialog.result["status"]
                )
                self.load_componentes(assento.produto_id)
                self.update_stats()
                messagebox.showinfo("Sucesso", "Assento atualizado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao atualizar assento: {e}")
                messagebox.showerror("Erro", f"Erro ao atualizar assento:\n{e}")

    def delete_assento(self):
        """Exclui assento selecionado"""
        selection = self.assentos_tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um assento para excluir")
            return

        # Pegar dados do assento
        item = self.assentos_tree.item(selection[0])
        assento_id = item['values'][0]
        modelo = item['values'][1]
        revestimento = item['values'][2]

        # Confirmar exclusão
        response = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o assento:\n\n"
            f"Modelo: {modelo}\n"
            f"Revestimento: {revestimento}\n\n"
            "⚠️ Isto também excluirá todas as combinações relacionadas a este assento.\n\n"
            "Esta ação não pode ser desfeita!"
        )

        if response:
            try:
                assento = self.db.get_assento_by_id(assento_id)
                if assento:
                    self.db.delete_assento(assento_id)
                    self.load_componentes(assento.produto_id)
                    self.update_stats()
                    messagebox.showinfo("Sucesso", "Assento excluído com sucesso!")
                else:
                    messagebox.showerror("Erro", "Assento não encontrado")
            except Exception as e:
                logger.error(f"Erro ao excluir assento: {e}")
                messagebox.showerror("Erro", f"Erro ao excluir assento:\n{e}")

    def add_pe_base_dialog(self):
        """Diálogo para adicionar pé/base"""
        produto_nome = self.produto_combo_var.get()
        if not produto_nome:
            messagebox.showwarning("Aviso", "Selecione um produto primeiro")
            return

        produto = next((p for p in self.produtos_data if p.nome_aba == produto_nome), None)
        if not produto:
            messagebox.showerror("Erro", "Produto não encontrado")
            return

        from .product_dialogs import PeBaseEditDialog

        dialog = PeBaseEditDialog(self.window, "Novo Pé/Base")
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.add_pe_base(
                    produto_id=produto.id,
                    nome=dialog.result["nome"],
                    ean=dialog.result["ean"],
                    codigo=dialog.result["codigo"],
                    quantidade=dialog.result["quantidade"]
                )
                self.load_componentes(produto.id)
                self.update_stats()
                messagebox.showinfo("Sucesso", "Pé/Base adicionado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao adicionar pé/base: {e}")
                messagebox.showerror("Erro", f"Erro ao adicionar pé/base:\n{e}")

    def edit_pe_base_dialog(self):
        """Diálogo para editar pé/base"""
        selection = self.pes_tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um pé/base para editar")
            return

        # Pegar dados do pé/base selecionado
        item = self.pes_tree.item(selection[0])
        pe_base_id = item['values'][0]

        # Buscar dados completos
        pe_base = self.db.get_pe_base_by_id(pe_base_id)
        if not pe_base:
            messagebox.showerror("Erro", "Pé/Base não encontrado")
            return

        from .product_dialogs import PeBaseEditDialog

        pe_base_data = {
            "nome": pe_base.nome,
            "ean": pe_base.ean,
            "codigo": pe_base.codigo,
            "quantidade": pe_base.quantidade,
            "status": pe_base.status
        }

        dialog = PeBaseEditDialog(self.window, "Editar Pé/Base", pe_base_data)
        self.window.wait_window(dialog.dialog)

        if dialog.result:
            try:
                self.db.update_pe_base(
                    pe_base_id=pe_base.id,
                    nome=dialog.result["nome"],
                    ean=dialog.result["ean"],
                    codigo=dialog.result["codigo"],
                    quantidade=dialog.result["quantidade"],
                    status=dialog.result["status"]
                )
                self.load_componentes(pe_base.produto_id)
                self.update_stats()
                messagebox.showinfo("Sucesso", "Pé/Base atualizado com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao atualizar pé/base: {e}")
                messagebox.showerror("Erro", f"Erro ao atualizar pé/base:\n{e}")

    def delete_pe_base(self):
                """Exclui pé/base selecionado"""
                selection = self.pes_tree.selection()
                if not selection:
                    messagebox.showwarning("Aviso", "Selecione um pé/base para excluir")
                    return

                # Pegar dados do pé/base
                item = self.pes_tree.item(selection[0])
                pe_base_id = item['values'][0]
                nome = item['values'][1]

                # Confirmar exclusão
                response = messagebox.askyesno(
                    "Confirmar Exclusão",
                    f"Tem certeza que deseja excluir o pé/base:\n\n"
                    f"Nome: {nome}\n\n"
                    "⚠️ Isto também excluirá todas as combinações relacionadas a este pé/base.\n\n"
                    "Esta ação não pode ser desfeita!"
                )

                if response:
                    try:
                        pe_base = self.db.get_pe_base_by_id(pe_base_id)
                        if pe_base:
                            self.db.delete_pe_base(pe_base_id)
                            self.load_componentes(pe_base.produto_id)
                            self.update_stats()
                            messagebox.showinfo("Sucesso", "Pé/Base excluído com sucesso!")
                        else:
                            messagebox.showerror("Erro", "Pé/Base não encontrado")
                    except Exception as e:
                        logger.error(f"Erro ao excluir pé/base: {e}")
                        messagebox.showerror("Erro", f"Erro ao excluir pé/base:\n{e}")

    def add_combinacao(self):
                """Adiciona nova combinação"""
                produto_nome = self.produto_comb_var.get()
                if not produto_nome:
                    messagebox.showwarning("Aviso", "Selecione um produto primeiro")
                    return

                produto = next((p for p in self.produtos_data if p.nome_aba == produto_nome), None)
                if not produto:
                    messagebox.showerror("Erro", "Produto não encontrado")
                    return

                from .product_dialogs import CombinationDialog

                dialog = CombinationDialog(self.window, self.db, produto.id)
                self.window.wait_window(dialog.dialog)

                if dialog.result:
                    try:
                        self.db.add_combinacao(
                            dialog.result["assento_id"],
                            dialog.result["pe_base_id"],
                            dialog.result["produto_id"]
                        )
                        self.load_combinacoes(produto.id)
                        self.update_stats()
                        messagebox.showinfo("Sucesso", "Combinação criada com sucesso!")
                    except Exception as e:
                        logger.error(f"Erro ao criar combinação: {e}")
                        if "UNIQUE constraint failed" in str(e):
                            messagebox.showwarning("Aviso", "Esta combinação já existe!")
                        else:
                            messagebox.showerror("Erro", f"Erro ao criar combinação:\n{e}")

    def generate_all_combinations(self):
                """Gera todas as combinações possíveis para um produto"""
                produto_nome = self.produto_comb_var.get()
                if not produto_nome:
                    messagebox.showwarning("Aviso", "Selecione um produto primeiro")
                    return

                produto = next((p for p in self.produtos_data if p.nome_aba == produto_nome), None)
                if not produto:
                    messagebox.showerror("Erro", "Produto não encontrado")
                    return

                # Confirmar geração
                response = messagebox.askyesno(
                    "Gerar Combinações",
                    f"Gerar todas as combinações possíveis para o produto '{produto_nome}'?\n\n"
                    "Isto criará uma combinação para cada assento com cada pé/base disponível.\n\n"
                    "Combinações duplicadas serão ignoradas."
                )

                if response:
                    try:
                        # Mostrar progresso
                        progress_dialog = self.create_progress_dialog("Gerando combinações...")

                        def generate():
                            try:
                                combinations_added = self.db.generate_combinations_for_produto(produto.id)

                                # Atualizar interface
                                self.window.after(0, lambda: self.finish_generation(progress_dialog, combinations_added,
                                                                                    produto.id))
                            except Exception:
                                self.window.after(0, lambda: self.handle_generation_error(progress_dialog, e)) # noqa: F821

                        thread = threading.Thread(target=generate, daemon=True)
                        thread.start()

                    except Exception as e:
                        logger.error(f"Erro ao gerar combinações: {e}")
                        messagebox.showerror("Erro", f"Erro ao gerar combinações:\n{e}")

    def create_progress_dialog(self, message: str):
                """Cria diálogo de progresso simples"""
                dialog = ctk.CTkToplevel(self.window)
                dialog.title("Processando...")
                dialog.geometry("300x150")
                dialog.transient(self.window)
                dialog.grab_set()

                # Centralizar
                dialog.update_idletasks()
                x = (dialog.winfo_screenwidth() - 300) // 2
                y = (dialog.winfo_screenheight() - 150) // 2
                dialog.geometry(f"300x150+{x}+{y}")

                frame = ctk.CTkFrame(dialog)
                frame.pack(fill="both", expand=True, padx=20, pady=20)

                ctk.CTkLabel(
                    frame,
                    text=message,
                    font=ctk.CTkFont(size=14)
                ).pack(expand=True)

                progress_bar = ctk.CTkProgressBar(frame)
                progress_bar.pack(fill="x", padx=20, pady=20)
                progress_bar.set(0.5)  # Indeterminado

                return dialog

    def finish_generation(self, progress_dialog, combinations_added: int, produto_id: int):
                """Finaliza geração de combinações"""
                try:
                    progress_dialog.destroy()
                    self.load_combinacoes(produto_id)
                    self.update_stats()

                    if combinations_added > 0:
                        messagebox.showinfo(
                            "Sucesso",
                            f"✅ {combinations_added} novas combinações foram geradas!"
                        )
                    else:
                        messagebox.showinfo(
                            "Informação",
                            "ℹ️ Todas as combinações possíveis já existem."
                        )
                except Exception as e:
                    logger.error(f"Erro ao finalizar geração: {e}")

    def handle_generation_error(self, progress_dialog, error):
                """Trata erro na geração de combinações"""
                try:
                    progress_dialog.destroy()
                    logger.error(f"Erro na geração: {error}")
                    messagebox.showerror("Erro", f"Erro ao gerar combinações:\n{error}")
                except Exception as e:
                    logger.error(f"Erro ao tratar erro de geração: {e}")

    def clear_combinations(self):
                """Limpa todas as combinações de um produto"""
                produto_nome = self.produto_comb_var.get()
                if not produto_nome:
                    messagebox.showwarning("Aviso", "Selecione um produto primeiro")
                    return

                produto = next((p for p in self.produtos_data if p.nome_aba == produto_nome), None)
                if not produto:
                    messagebox.showerror("Erro", "Produto não encontrado")
                    return

                # Confirmar limpeza
                response = messagebox.askyesno(
                    "Limpar Combinações",
                    f"Tem certeza que deseja excluir TODAS as combinações do produto '{produto_nome}'?\n\n"
                    "⚠️ Esta ação não pode ser desfeita!"
                )

                if response:
                    try:
                        deleted_count = self.db.clear_combinacoes_by_produto(produto.id)
                        self.load_combinacoes(produto.id)
                        self.update_stats()
                        messagebox.showinfo("Sucesso", f"✅ {deleted_count} combinações foram excluídas!")
                    except Exception as e:
                        logger.error(f"Erro ao limpar combinações: {e}")
                        messagebox.showerror("Erro", f"Erro ao limpar combinações:\n{e}")

    def search_by_ean(self):
        """Busca produto por EAN"""
        ean = self.search_ean_var.get().strip()
        if not ean:
            messagebox.showwarning("Aviso", "Digite um código EAN")
            return

        try:
            result = self.db.search_by_ean(ean)

            if result:
                if result["tipo"] == "assento":
                    text = (f"✅ EAN Encontrado!\n\n"
                            f"🪑 Tipo: Assento\n"
                            f"📦 Produto: {result['produto']}\n"
                            f"🏷️ Modelo: {result['modelo']}\n"
                            f"🎨 Revestimento: {result['revestimento']}")
                else:
                    text = (f"✅ EAN Encontrado!\n\n"
                            f"🦵 Tipo: Pé/Base\n"
                            f"📦 Produto: {result['produto']}\n"
                            f"🏷️ Nome: {result['nome']}\n"
                            f"📊 Quantidade: {result['quantidade']}")

                self.result_label.configure(text=text, text_color=("green", "lightgreen"))
            else:
                self.result_label.configure(
                    text=f"❌ EAN não encontrado: {ean}",
                    text_color=("red", "lightcoral")
                )

        except Exception as e:
            logger.error(f"Erro na busca: {e}")
            self.result_label.configure(
                text=f"❌ Erro na busca: {e}",
                text_color=("red", "lightcoral")
            )

    def import_spreadsheet(self):
        """Importa dados da planilha"""
        try:
            # Selecionar arquivo
            file_path = filedialog.askopenfilename(
                title="Selecionar Planilha de Produtos",
                filetypes=[
                    ("Excel files", "*.xlsx *.xls"),
                    ("All files", "*.*")
                ]
            )

            if not file_path:
                return

            file_path = Path(file_path)
            if not file_path.exists():
                messagebox.showerror("Erro", "Arquivo não encontrado")
                return

            # ✅ DIÁLOGO SIMPLIFICADO
            response = messagebox.askyesnocancel(
                "Importar Planilha",
                "Como deseja importar?\n\n"
                "SIM = Limpar dados existentes e reimportar\n"
                "NÃO = Adicionar aos dados existentes\n"
                "CANCELAR = Cancelar operação\n\n"
                "ℹ️ NOTA: Combinações serão geradas manualmente na interface."
            )

            if response is None:  # Cancelar
                return

            # Importar em thread separada
            self.import_in_progress = True
            self.update_import_ui(True)

            def run_import():
                try:
                    from ...services.product_importer import ProductImporter

                    importer = ProductImporter(self.db_path)

                    # ✅ USAR APENAS OS PARÂMETROS QUE EXISTEM
                    if response:  # SIM = Limpar e reimportar
                        result = importer.import_from_excel(file_path, clear_existing=True)
                    else:  # NÃO = Adicionar
                        result = importer.import_from_excel(file_path, clear_existing=False)

                    # Atualizar interface
                    self.window.after(0, lambda: self.import_completed(result))

                except Exception as e:
                    error_msg = f"Erro na importação: {str(e)}"
                    logger.error(error_msg)
                    self.window.after(0, lambda: self.import_error(error_msg))

            thread = threading.Thread(target=run_import, daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"Erro ao iniciar importação: {e}")
            messagebox.showerror("Erro", f"Erro ao iniciar importação:\n{e}")

    def update_import_ui(self, importing: bool):
        """Atualiza interface durante importação"""
        if importing:
            # Criar diálogo de progresso se não existir
            if not hasattr(self, 'import_dialog'):
                self.create_import_dialog()
        else:
            # Fechar diálogo de progresso
            if hasattr(self, 'import_dialog') and self.import_dialog:
                try:
                    self.import_dialog.destroy()
                    self.import_dialog = None
                except Exception:
                    pass

    def create_import_dialog(self):
        """Cria diálogo de progresso da importação"""
        self.import_dialog = ctk.CTkToplevel(self.window)
        self.import_dialog.title("📥 Importando Produtos")
        self.import_dialog.geometry("500x200")
        self.import_dialog.transient(self.window)
        self.import_dialog.grab_set()

        # Centralizar
        self.import_dialog.update_idletasks()
        x = (self.import_dialog.winfo_screenwidth() - 500) // 2
        y = (self.import_dialog.winfo_screenheight() - 200) // 2
        self.import_dialog.geometry(f"500x200+{x}+{y}")

        frame = ctk.CTkFrame(self.import_dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Status
        self.import_status_var = tk.StringVar(value="Iniciando importação...")
        status_label = ctk.CTkLabel(
            frame,
            textvariable=self.import_status_var,
            font=ctk.CTkFont(size=14)
        )
        status_label.pack(pady=20)

        # Progress bar
        self.import_progress_var = tk.DoubleVar()
        self.import_progress_bar = ctk.CTkProgressBar(
            frame,
            variable=self.import_progress_var,
            height=20
        )
        self.import_progress_bar.pack(fill="x", padx=20, pady=20)

    def update_import_progress(self, value: float):
        """Atualiza progresso da importação"""
        try:
            if hasattr(self, 'import_progress_var'):
                self.window.after(0, lambda: self.import_progress_var.set(value))
        except Exception:
            pass

    def update_import_status(self, message: str):
        """Atualiza status da importação"""
        try:
            if hasattr(self, 'import_status_var'):
                self.window.after(0, lambda: self.import_status_var.set(message))
        except Exception:
            pass

    def import_completed(self, result):
        """Callback quando importação é concluída"""
        try:
            self.update_import_ui(False)
            self.import_in_progress = False

            # Atualizar listas
            self.load_produtos()
            self.update_stats()

            # ✅ CORRIGIR: result é um ImportResult, não um dict
            if result.errors:
                error_summary = "\n".join(result.errors[:5])
                if len(result.errors) > 5:
                    error_summary += f"\n... e mais {len(result.errors) - 5} erros"

                message = (
                    f"✅ Importação concluída com avisos:\n\n"
                    f"📋 Produtos: {result.total_produtos}\n"
                    f"🪑 Assentos: {result.total_assentos}\n"
                    f"🦵 Pés/Bases: {result.total_pes_bases}\n"
                    f"🔧 Componentes Especiais: {result.total_componentes_especiais}\n"
                    f"🔗 Combinações: {result.total_combinacoes}\n"
                    f"⏱️ Tempo: {result.processing_time:.2f}s\n\n"
                    f"⚠️ Erros encontrados:\n{error_summary}"
                )
                messagebox.showwarning("Importação Concluída", message)
            else:
                message = (
                    f"✅ Importação concluída com sucesso!\n\n"
                    f"📋 Produtos importados: {result.total_produtos}\n"
                    f"🪑 Assentos importados: {result.total_assentos}\n"
                    f"🦵 Pés/Bases importados: {result.total_pes_bases}\n"
                    f"🔧 Componentes Especiais: {result.total_componentes_especiais}\n"
                    f"🔗 Combinações geradas: {result.total_combinacoes}\n"
                    f"⏱️ Tempo de processamento: {result.processing_time:.2f}s\n\n"
                    f"💡 Use o botão 'Gerar Combinações' para criar combinações específicas."
                )
                messagebox.showinfo("Sucesso!", message)

            # ✅ MOSTRAR WARNINGS SE HOUVER
            if result.warnings:
                warnings_summary = "\n".join(result.warnings[:3])
                if len(result.warnings) > 3:
                    warnings_summary += f"\n... e mais {len(result.warnings) - 3} avisos"

                messagebox.showinfo(
                    "Avisos da Importação",
                    f"ℹ️ Avisos encontrados:\n\n{warnings_summary}"
                )

        except Exception as e:
            logger.error(f"Erro ao finalizar importação: {e}")
            messagebox.showerror("Erro", f"Erro ao processar resultado da importação:\n{e}")

    def import_error(self, error_msg: str):
        """Callback quando há erro na importação"""
        try:
            self.update_import_ui(False)
            self.import_in_progress = False

            # Atualizar listas mesmo com erro (pode ter importado parcialmente)
            try:
                self.load_produtos()
                self.update_stats()
            except Exception:
                pass  # Ignorar erros de atualização

            messagebox.showerror("Erro na Importação", f"❌ Falha na importação:\n\n{error_msg}")

        except Exception as e:
            logger.error(f"Erro ao tratar erro de importação: {e}")
            # Último recurso: mostrar erro básico
            try:
                messagebox.showerror("Erro Crítico", f"Erro crítico no sistema:\n{e}")
            except Exception:
                pass

    def on_closing(self):
        """Fecha a janela"""
        self.window.destroy()


class ProductDialog:
    """Diálogo simples para adicionar produto"""

    def __init__(self, parent, title):
        self.result = None

        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x200")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 100
        self.dialog.geometry(f"400x200+{x}+{y}")

        # Widgets
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            main_frame,
            text="Nome da Aba (Produto):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(20, 10))

        self.nome_var = tk.StringVar()
        self.nome_entry = ctk.CTkEntry(
            main_frame,
            textvariable=self.nome_var,
            placeholder_text="Ex: Alice, Aline, Anitta...",
            width=300
        )
        self.nome_entry.pack(pady=(0, 20))

        # Botões
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 20))

        ctk.CTkButton(
            btn_frame,
            text="✅ Salvar",
            command=self.save,
            width=120
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120
        ).pack(side="right")

        # Focus e bind
        self.nome_entry.focus()
        self.nome_entry.bind("<Return>", lambda e: self.save())
        self.dialog.bind("<Escape>", lambda e: self.cancel())

    def save(self):
        nome = self.nome_var.get().strip()
        if not nome:
            messagebox.showwarning("Aviso", "Digite o nome da aba")
            return

        self.result = {"nome_aba": nome}
        self.dialog.destroy()

    def cancel(self):
        self.dialog.destroy()