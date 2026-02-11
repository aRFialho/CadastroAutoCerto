"""Janela principal para gerenciamento de custos por fornecedor"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging


logger = logging.getLogger(__name__)

class CostsManagerWindow:
    """Janela principal de gerenciamento de custos"""

    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self.costs_db = None
        self.fornecedores_data = []
        self.custos_data = []
        self.current_fornecedor = None

        # Inicializar banco de custos
        self.init_costs_database()

        # Criar janela
        self.create_window()

    def init_costs_database(self):
        """Inicializa banco de dados de custos"""
        try:
            from ...core.config import load_config
            from ...core.costs_database import CostsDatabase

            config = load_config()
            costs_db_path = config.output_dir / "costs.db"
            self.costs_db = CostsDatabase(costs_db_path)

            logger.info(f"Banco de custos inicializado: {costs_db_path}")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco de custos: {e}")
            messagebox.showerror("Erro", f"Erro ao inicializar banco de custos:\n{e}")
            self.costs_db = None

    def create_window(self):
        """Cria a janela principal"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("💰 Gerenciamento de Custos por Fornecedor")
        self.window.geometry("1400x800")
        self.window.transient(self.parent)

        # Centralizar janela
        self.center_window()

        # Criar interface
        self.create_widgets()

        # Carregar dados iniciais
        self.load_fornecedores()

    def center_window(self):
        """Centraliza a janela"""
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 1400) // 2
        y = (self.window.winfo_screenheight() - 800) // 2
        self.window.geometry(f"1400x800+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="💰 Gerenciamento de Custos por Fornecedor",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Frame de conteúdo dividido
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Painel esquerdo - Fornecedores
        self.create_suppliers_panel(content_frame)

        # Painel direito - Custos
        self.create_costs_panel(content_frame)

        # Barra de status
        self.create_status_bar(main_frame)

    def create_suppliers_panel(self, parent):
        """Cria painel de fornecedores"""
        # Frame dos fornecedores
        suppliers_frame = ctk.CTkFrame(parent)
        suppliers_frame.pack(side="left", fill="both", expand=True, padx=(20, 10), pady=20)

        # Cabeçalho
        header_frame = ctk.CTkFrame(suppliers_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header_frame,
            text="🏢 Fornecedores",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")

        # Botões do cabeçalho
        buttons_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        buttons_frame.pack(side="right")

        ctk.CTkButton(
            buttons_frame,
            text="📥 Da Planilha",
            command=self.import_supplier_from_spreadsheet,
            width=100,
            height=30,
            fg_color="#2B8B3D",  # Verde diferenciado
            hover_color="#228B22"
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            buttons_frame,
            text="➕ Novo",
            command=self.add_supplier_dialog,
            width=80,
            height=30
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            buttons_frame,
            text="✏️ Editar",
            command=self.edit_supplier_dialog,
            width=80,
            height=30
        ).pack(side="right", padx=(5, 0))

        # Lista de fornecedores
        self.create_suppliers_list(suppliers_frame)

        # Estatísticas dos fornecedores
        self.create_suppliers_stats(suppliers_frame)

    def create_suppliers_list(self, parent):
        """Cria lista de fornecedores"""
        list_frame = ctk.CTkFrame(parent)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Treeview para fornecedores
        columns = ("ID", "Nome", "Código", "Total Produtos", "Última Importação")
        self.suppliers_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=15
        )

        # Configurar colunas
        column_configs = {
            "ID": (50, "center"),
            "Nome": (200, "w"),
            "Código": (100, "center"),
            "Total Produtos": (120, "center"),
            "Última Importação": (150, "center")
        }

        for col, (width, anchor) in column_configs.items():
            self.suppliers_tree.heading(col, text=col)
            self.suppliers_tree.column(col, width=width, anchor=anchor)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.suppliers_tree.yview)
        self.suppliers_tree.configure(yscrollcommand=v_scrollbar.set)

        # Pack
        self.suppliers_tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        v_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)

        # Bind eventos
        self.suppliers_tree.bind("<<TreeviewSelect>>", self.on_supplier_select)
        self.suppliers_tree.bind("<Double-1>", lambda e: self.edit_supplier_dialog())

    def create_suppliers_stats(self, parent):
        """Cria estatísticas dos fornecedores"""
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            stats_frame,
            text="📊 Estatísticas",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        # Labels de estatísticas
        self.stats_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.total_suppliers_label = ctk.CTkLabel(self.stats_frame, text="Total de Fornecedores: 0")
        self.total_suppliers_label.pack(anchor="w", pady=2)

        self.total_products_label = ctk.CTkLabel(self.stats_frame, text="Total de Produtos: 0")
        self.total_products_label.pack(anchor="w", pady=2)

    def create_costs_panel(self, parent):
        """Cria painel de custos"""
        # Frame dos custos
        costs_frame = ctk.CTkFrame(parent)
        costs_frame.pack(side="right", fill="both", expand=True, padx=(10, 20), pady=20)

        # Cabeçalho
        header_frame = ctk.CTkFrame(costs_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        self.costs_title_label = ctk.CTkLabel(
            header_frame,
            text="💰 Custos - Selecione um fornecedor",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.costs_title_label.pack(side="left")

        # Botões do cabeçalho
        buttons_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        buttons_frame.pack(side="right")

        self.import_button = ctk.CTkButton(
            buttons_frame,
            text="📥 Importar",
            command=self.import_costs_dialog,
            width=100,
            height=30,
            state="disabled"
        )
        self.import_button.pack(side="right", padx=(5, 0))

        self.export_button = ctk.CTkButton(
            buttons_frame,
            text="📤 Exportar",
            command=self.export_costs,
            width=100,
            height=30,
            state="disabled"
        )
        self.export_button.pack(side="right", padx=(5, 0))

        # Busca
        search_frame = ctk.CTkFrame(costs_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 10))

        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="Digite código, nome ou categoria...",
            width=300
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_change)

        ctk.CTkButton(
            search_frame,
            text="🔍",
            command=self.search_costs,
            width=40,
            height=30
        ).pack(side="left")

        # Lista de custos
        self.create_costs_list(costs_frame)

    def create_costs_list(self, parent):
        """Cria lista de custos"""
        list_frame = ctk.CTkFrame(parent)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Treeview para custos
        columns = (
            "ID", "Código", "Nome", "EAN", "Custo Unit.", "Custo Total",
            "Preço Venda", "Markup %", "Categoria", "Estoque"
        )
        self.costs_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=20
        )

        # Configurar colunas
        column_configs = {
            "ID": (50, "center"),
            "Código": (100, "center"),
            "Nome": (200, "w"),
            "EAN": (120, "center"),
            "Custo Unit.": (100, "center"),
            "Custo Total": (100, "center"),
            "Preço Venda": (100, "center"),
            "Markup %": (80, "center"),
            "Categoria": (120, "w"),
            "Estoque": (80, "center")
        }

        for col, (width, anchor) in column_configs.items():
            self.costs_tree.heading(col, text=col)
            self.costs_tree.column(col, width=width, anchor=anchor)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.costs_tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient="horizontal", command=self.costs_tree.xview)
        self.costs_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Pack
        self.costs_tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        v_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)
        h_scrollbar.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        # Bind eventos
        self.costs_tree.bind("<Double-1>", self.edit_cost_dialog)

    def create_status_bar(self, parent):
        """Cria barra de status"""
        self.status_frame = ctk.CTkFrame(parent, height=30)
        self.status_frame.pack(fill="x", padx=20, pady=(0, 20))
        self.status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Pronto",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="left", padx=15, pady=5)

    def load_fornecedores(self):
        """Carrega a lista de fornecedores"""
        try:
            if self.costs_db is None:
                return

            # CORREÇÃO: Usar list_fornecedores() em vez de get_fornecedores()
            self.fornecedores_data = self.costs_db.list_fornecedores(ativo_apenas=True)

            # Atualizar a lista na interface
            self.update_suppliers_list()

            # Atualizar estatísticas
            self.update_stats()

            self.status_label.configure(text=f"Carregados {len(self.fornecedores_data)} fornecedores")

        except Exception as e:
            logger.error(f"Erro ao carregar fornecedores: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar fornecedores: {e}")

    def update_suppliers_list(self):
        """Atualiza lista de fornecedores"""
        try:
            # Limpar lista
            for item in self.suppliers_tree.get_children():
                self.suppliers_tree.delete(item)

            # Adicionar fornecedores
            for fornecedor in self.fornecedores_data:
                ultima_importacao = ""
                if fornecedor.ultima_importacao:
                    ultima_importacao = fornecedor.ultima_importacao.strftime("%d/%m/%Y %H:%M")

                values = (
                    fornecedor.id,
                    fornecedor.nome,
                    fornecedor.codigo or "-",
                    fornecedor.total_produtos,
                    ultima_importacao
                )
                self.suppliers_tree.insert("", "end", values=values)

        except Exception as e:
            logger.error(f"Erro ao atualizar lista de fornecedores: {e}")

    def update_stats(self):
        """Atualiza estatísticas"""
        try:
            if self.costs_db is None:
                self.total_suppliers_label.configure(text="Total de Fornecedores: 0")
                self.total_products_label.configure(text="Total de Produtos: 0")
                return

            stats = self.costs_db.get_stats()

            self.total_suppliers_label.configure(text=f"Total de Fornecedores: {stats.get('total_fornecedores', 0)}")
            self.total_products_label.configure(text=f"Total de Produtos: {stats.get('total_produtos', 0)}")

        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas: {e}")
            self.total_suppliers_label.configure(text="Total de Fornecedores: 0")
            self.total_products_label.configure(text="Total de Produtos: 0")

    def on_supplier_select(self, event):
        """Evento de seleção de fornecedor"""
        try:
            selection = self.suppliers_tree.selection()
            if not selection:
                self.current_fornecedor = None
                self.costs_title_label.configure(text="💰 Custos - Selecione um fornecedor")
                self.import_button.configure(state="disabled")
                self.export_button.configure(state="disabled")
                self.clear_costs_list()
                return

            item = self.suppliers_tree.item(selection[0])
            fornecedor_id = item['values'][0]

            # Buscar fornecedor
            if self.costs_db:
                self.current_fornecedor = self.costs_db.get_fornecedor_by_id(fornecedor_id)

                if self.current_fornecedor:
                    self.costs_title_label.configure(text=f"💰 Custos - {self.current_fornecedor.nome}")
                    self.import_button.configure(state="normal")
                    self.export_button.configure(state="normal")
                    self.load_costs_for_supplier(self.current_fornecedor.nome)

        except Exception as e:
            logger.error(f"Erro ao selecionar fornecedor: {e}")

    def load_costs_for_supplier(self, fornecedor_nome: str):
        """Carrega custos para um fornecedor"""
        try:
            if self.costs_db:
                self.custos_data = self.costs_db.get_custos_by_fornecedor(fornecedor_nome)
                self.update_costs_list()
                self.status_label.configure(text=f"Carregados {len(self.custos_data)} produtos de {fornecedor_nome}")

        except Exception as e:
            logger.error(f"Erro ao carregar custos: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar custos:\n{e}")

    def update_costs_list(self):
        """Atualiza lista de custos"""
        try:
            # Limpar lista
            for item in self.costs_tree.get_children():
                self.costs_tree.delete(item)

            # Adicionar custos
            for custo in self.custos_data:
                values = (
                    custo.id,
                    custo.codigo_produto,
                    custo.nome_produto[:30] + "..." if len(custo.nome_produto) > 30 else custo.nome_produto,
                    custo.ean,
                    f"R$ {custo.custo_unitario:.2f}" if custo.custo_unitario else "-",
                    f"R$ {custo.custo_total:.2f}" if custo.custo_total else "-",
                    f"R$ {custo.preco_venda_sugerido:.2f}" if custo.preco_venda_sugerido else "-",
                    f"{custo.percentual_markup:.1f}%" if custo.percentual_markup else "-",
                    custo.categoria[:15] + "..." if len(custo.categoria) > 15 else custo.categoria,
                    custo.estoque_atual
                )
                self.costs_tree.insert("", "end", values=values)

        except Exception as e:
            logger.error(f"Erro ao atualizar lista de custos: {e}")

    def clear_costs_list(self):
        """Limpa lista de custos"""
        for item in self.costs_tree.get_children():
            self.costs_tree.delete(item)

    def on_search_change(self, event):
        """Evento de mudança na busca"""
        # Implementar busca em tempo real se necessário
        pass

    def search_costs(self):
        """Busca custos"""
        if not self.current_fornecedor:
            return

        try:
            search_term = self.search_var.get().strip()

            if search_term:
                # Buscar com filtros
                filtered_costs = []
                for custo in self.custos_data:
                    if (search_term.lower() in custo.codigo_produto.lower() or
                            search_term.lower() in custo.nome_produto.lower() or
                            search_term.lower() in custo.categoria.lower() or
                            search_term.lower() in custo.ean.lower()):
                        filtered_costs.append(custo)

                # Atualizar lista temporariamente
                original_data = self.custos_data
                self.custos_data = filtered_costs
                self.update_costs_list()
                self.custos_data = original_data

                self.status_label.configure(text=f"Encontrados {len(filtered_costs)} produtos")
            else:
                self.update_costs_list()
                self.status_label.configure(text=f"Mostrando todos os {len(self.custos_data)} produtos")

        except Exception as e:
            logger.error(f"Erro na busca: {e}")

    def add_supplier_dialog(self):
        """Abre diálogo para adicionar fornecedor"""
        try:
            from .supplier_form_dialog import SupplierFormDialog

            if self.costs_db is None:
                messagebox.showerror("Erro", "Banco de dados não disponível")
                return

            dialog = SupplierFormDialog(self.window, self.costs_db)

            if dialog.result == "success":
                self.load_fornecedores()
                self.status_label.configure(text="Fornecedor adicionado com sucesso")

        except Exception as e:
            logger.error(f"Erro ao adicionar fornecedor: {e}")
            messagebox.showerror("Erro", f"Erro ao adicionar fornecedor:\n{e}")

    def edit_supplier_dialog(self):
        """Abre diálogo para editar fornecedor"""
        if not self.current_fornecedor:
            messagebox.showwarning("Aviso", "Selecione um fornecedor primeiro")
            return

        try:
            from .supplier_form_dialog import SupplierFormDialog

            dialog = SupplierFormDialog(self.window, self.costs_db, self.current_fornecedor)

            if dialog.result == "success":
                self.load_fornecedores()
                self.status_label.configure(text="Fornecedor atualizado com sucesso")

        except Exception as e:
            logger.error(f"Erro ao editar fornecedor: {e}")
            messagebox.showerror("Erro", f"Erro ao editar fornecedor:\n{e}")

    def import_costs_dialog(self):
        """Abre diálogo para importar custos"""
        if not self.current_fornecedor:
            messagebox.showwarning("Aviso", "Selecione um fornecedor primeiro")
            return

        try:
            from .costs_import_dialog import CostsImportDialog

            dialog = CostsImportDialog(self.window, self.costs_db, self.current_fornecedor)

            if dialog.result == "success":
                self.load_costs_for_supplier(self.current_fornecedor.nome)
                self.load_fornecedores()  # Atualizar estatísticas
                self.status_label.configure(text="Custos importados com sucesso")

        except Exception as e:
            logger.error(f"Erro ao importar custos: {e}")
            messagebox.showerror("Erro", f"Erro ao importar custos:\n{e}")

    def export_costs(self):
        """Exporta custos para Excel"""
        if not self.current_fornecedor or not self.custos_data:
            messagebox.showwarning("Aviso", "Não há dados para exportar")
            return

        try:
            # Selecionar arquivo
            file_path = filedialog.asksaveasfilename(
                title="Exportar Custos",
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                initialname=f"custos_{self.current_fornecedor.nome.replace(' ', '_')}.xlsx"
            )

            if file_path:
                self.export_costs_to_excel(file_path)

        except Exception as e:
            logger.error(f"Erro ao exportar custos: {e}")
            messagebox.showerror("Erro", f"Erro ao exportar custos:\n{e}")

    def export_costs_to_excel(self, file_path: str):
        """Exporta custos para arquivo Excel"""
        try:
            import pandas as pd

            # Preparar dados
            data = []
            for custo in self.custos_data:
                data.append({
                    "Código": custo.codigo_produto,
                    "Nome": custo.nome_produto,
                    "EAN": custo.ean,
                    "Referência": custo.referencia,
                    "Fornecedor": custo.fornecedor,
                    "Custo Unitário": custo.custo_unitario,
                    "Custo com IPI": custo.custo_com_ipi,
                    "Custo com Frete": custo.custo_com_frete,
                    "Custo Total": custo.custo_total,
                    "% IPI": custo.percentual_ipi,
                    "% Frete": custo.percentual_frete,
                    "% Markup": custo.percentual_markup,
                    "Preço Venda Sugerido": custo.preco_venda_sugerido,
                    "Preço Promocional": custo.preco_promocional,
                    "Unidade": custo.unidade,
                    "Categoria": custo.categoria,
                    "Subcategoria": custo.subcategoria,
                    "Estoque Mínimo": custo.estoque_minimo,
                    "Estoque Atual": custo.estoque_atual,
                    "Observações": custo.observacoes,
                    "Data Importação": custo.data_importacao.strftime("%d/%m/%Y %H:%M") if custo.data_importacao else "",
                    "Arquivo Origem": custo.arquivo_origem
                })

            # Criar DataFrame e salvar
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False, sheet_name=f"Custos_{self.current_fornecedor.nome}")

            messagebox.showinfo("Sucesso", f"Custos exportados para:\n{file_path}")
            self.status_label.configure(text=f"Exportados {len(data)} produtos para Excel")

        except Exception as e:
            logger.error(f"Erro ao exportar para Excel: {e}")
            raise

    def edit_cost_dialog(self, event):
        """Abre diálogo para editar custo"""
        try:
            selection = self.costs_tree.selection()
            if not selection:
                return

            item = self.costs_tree.item(selection[0])
            custo_id = item['values'][0]

            # Buscar custo
            custo = None
            for c in self.custos_data:
                if c.id == custo_id:
                    custo = c
                    break

            if custo:
                # Implementar diálogo de edição de custo
                messagebox.showinfo("Info", f"Editar custo: {custo.nome_produto}")

        except Exception as e:
            logger.error(f"Erro ao editar custo: {e}")

    def import_supplier_from_spreadsheet(self):
                """Importa fornecedor e custos diretamente de planilha"""
                try:
                    from .supplier_spreadsheet_import_dialog import SupplierSpreadsheetImportDialog

                    dialog = SupplierSpreadsheetImportDialog(self.window, self.costs_db)

                    if dialog.result == "success":
                        self.load_fornecedores()
                        self.status_label.configure(text="Fornecedor e custos importados com sucesso")

                except Exception as e:
                    logger.error(f"Erro ao importar fornecedor da planilha: {e}")
                    messagebox.showerror("Erro", f"Erro ao importar fornecedor da planilha:\n{e}")

    def view_custos_fornecedor(self, fornecedor):
        """Abre uma nova janela para visualizar os custos do fornecedor"""
        try:
            # Criar nova janela
            window = ctk.CTkToplevel(self.window)
            window.title(f"Custos de {fornecedor.nome}")
            window.geometry("1200x700")  # Mais ampla
            window.transient(self.window)

            # Frame principal
            main_frame = ctk.CTkFrame(window)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # Título
            ctk.CTkLabel(
                main_frame,
                text=f"💰 Custos de {fornecedor.nome}",
                font=ctk.CTkFont(size=18, weight="bold")
            ).pack(pady=(10, 20))

            # Frame da tabela
            table_frame = ctk.CTkFrame(main_frame)
            table_frame.pack(fill="both", expand=True)

            # CORREÇÃO: Usar get_custos_by_fornecedor() que existe na sua classe
            custos = self.costs_db.get_custos_by_fornecedor(fornecedor.nome, ativo_apenas=True)

            if custos:
                # Definir colunas para exibição
                columns = (
                    "ID", "Código", "Nome", "EAN", "Custo Unit.", "Custo Total",
                    "Preço Venda", "Markup %", "Categoria", "Estoque", "Data Import."
                )

                # Criar Treeview
                tree = ttk.Treeview(table_frame, columns=columns, show="headings")

                # Configurar colunas
                column_configs = {
                    "ID": (50, "center"),
                    "Código": (100, "center"),
                    "Nome": (250, "w"),
                    "EAN": (120, "center"),
                    "Custo Unit.": (100, "center"),
                    "Custo Total": (100, "center"),
                    "Preço Venda": (100, "center"),
                    "Markup %": (80, "center"),
                    "Categoria": (120, "w"),
                    "Estoque": (80, "center"),
                    "Data Import.": (120, "center")
                }

                for col, (width, anchor) in column_configs.items():
                    tree.heading(col, text=col)
                    tree.column(col, width=width, anchor=anchor)

                # Scrollbars
                v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
                h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
                tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

                # Inserir dados
                for custo in custos:
                    data_import = ""
                    if custo.data_importacao:
                        data_import = custo.data_importacao.strftime("%d/%m/%Y")

                    values = (
                        custo.id,
                        custo.codigo_produto,
                        custo.nome_produto[:40] + "..." if len(custo.nome_produto) > 40 else custo.nome_produto,
                        custo.ean,
                        f"R\$ {custo.custo_unitario:.2f}" if custo.custo_unitario else "-",
                        f"R\$ {custo.custo_total:.2f}" if custo.custo_total else "-",
                        f"R\$ {custo.preco_venda_sugerido:.2f}" if custo.preco_venda_sugerido else "-",
                        f"{custo.percentual_markup:.1f}%" if custo.percentual_markup else "-",
                        custo.categoria[:15] + "..." if len(custo.categoria) > 15 else custo.categoria,
                        custo.estoque_atual,
                        data_import
                    )
                    tree.insert("", "end", values=values)

                # Pack da tabela e scrollbars
                tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
                v_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)

                # Frame para scrollbar horizontal
                h_scroll_frame = ctk.CTkFrame(table_frame, height=20)
                h_scroll_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 15))
                h_scrollbar.pack(in_=h_scroll_frame, fill="x")

            else:
                ctk.CTkLabel(
                    table_frame,
                    text="Nenhum custo encontrado para este fornecedor",
                    font=ctk.CTkFont(size=14)
                ).pack(pady=50)

        except Exception as e:
            logger.error(f"Erro ao visualizar custos: {e}")
            messagebox.showerror("Erro", f"Erro ao visualizar custos: {e}")

    def view_dados_fornecedor(self, fornecedor):
        """Abre uma nova janela para visualizar os dados do fornecedor"""
        try:
            # Criar nova janela
            window = ctk.CTkToplevel(self.window)
            window.title(f"Dados de {fornecedor.nome}")
            window.geometry("800x600")
            window.transient(self.window)

            # Frame principal
            main_frame = ctk.CTkFrame(window)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # Título
            ctk.CTkLabel(
                main_frame,
                text=f"🏢 Dados de {fornecedor.nome}",
                font=ctk.CTkFont(size=18, weight="bold")
            ).pack(pady=(10, 20))

            # Frame de dados
            data_frame = ctk.CTkScrollableFrame(main_frame)
            data_frame.pack(fill="both", expand=True)

            # Exibir dados do fornecedor
            dados = [
                ("ID", fornecedor.id),
                ("Nome", fornecedor.nome),
                ("Código", fornecedor.codigo),
                ("CNPJ", fornecedor.cnpj),
                ("Contato", fornecedor.contato),
                ("Email", fornecedor.email),
                ("Telefone", fornecedor.telefone),
                ("Endereço", fornecedor.endereco),
                ("Linha Cabeçalho", fornecedor.linha_cabecalho),
                ("Total Produtos", fornecedor.total_produtos),
                ("Última Importação",
                 fornecedor.ultima_importacao.strftime("%d/%m/%Y %H:%M") if fornecedor.ultima_importacao else "Nunca"),
                ("Ativo", "Sim" if fornecedor.ativo else "Não"),
                ("Criado em", fornecedor.created_at.strftime("%d/%m/%Y %H:%M") if fornecedor.created_at else "-"),
                ("Atualizado em", fornecedor.updated_at.strftime("%d/%m/%Y %H:%M") if fornecedor.updated_at else "-")
            ]

            for label, value in dados:
                row_frame = ctk.CTkFrame(data_frame)
                row_frame.pack(fill="x", pady=2, padx=10)

                ctk.CTkLabel(
                    row_frame,
                    text=f"{label}:",
                    font=ctk.CTkFont(weight="bold"),
                    width=150
                ).pack(side="left", padx=10, pady=5)

                ctk.CTkLabel(
                    row_frame,
                    text=str(value) if value is not None else "-"
                ).pack(side="left", padx=10, pady=5)

        except Exception as e:
            logger.error(f"Erro ao visualizar dados do fornecedor: {e}")
            messagebox.showerror("Erro", f"Erro ao visualizar dados: {e}")

    def show(self):
        """Mostra a janela"""
        if self.window:
            self.window.deiconify()
            self.window.lift()
            self.window.focus()