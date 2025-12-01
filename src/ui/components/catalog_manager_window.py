"""Interface para gerenciamento do catálogo de produtos"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
import threading

from ...core.product_catalog_database import ProductCatalogDatabase, ProdutoCatalogo
from .catalog_import_dialog import CatalogImportDialog

logger = logging.getLogger(__name__)


class CatalogManagerWindow:
    """Janela de gerenciamento do catálogo de produtos"""

    def __init__(self, parent, db_path: Path):
        self.parent = parent
        self.db_path = db_path  # ✅ Este é o caminho do banco
        self.db = ProductCatalogDatabase(db_path)  # ✅ Instância do banco
        self.window = None

        # Variáveis de controle
        self.selected_produto = None
        self.produtos_data = []
        self.current_page = 0
        self.items_per_page = 100
        self.total_items = 0
        self.search_term = ""

        self.setup_window()
        self.create_widgets()
        self.load_data()

    def setup_window(self):
        """Configura a janela principal"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("📋 Gerenciador do Catálogo de Produtos")
        self.window.geometry("1600x1000")
        self.window.minsize(1400, 800)

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
            text="📋 Gerenciador do Catálogo de Produtos",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Frame de conteúdo com abas
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Aba 1: Lista de Produtos
        self.create_products_tab()

        # Aba 2: Busca Avançada
        self.create_search_tab()

        # Aba 3: Estatísticas
        self.create_stats_tab()

        # Frame de botões inferiores
        self.create_bottom_buttons(main_frame)

    def create_products_tab(self):
        """Cria aba de lista de produtos"""
        products_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(products_frame, text="📦 Produtos")

        # Barra de ferramentas
        self.create_toolbar(products_frame)

        # Lista de produtos
        self.create_products_list(products_frame)

        # Paginação
        self.create_pagination(products_frame)

    def create_toolbar(self, parent):
        """Cria barra de ferramentas"""
        toolbar_frame = ctk.CTkFrame(parent)
        toolbar_frame.pack(fill="x", padx=20, pady=(20, 10))

        # Linha 1: Busca
        search_frame = ctk.CTkFrame(toolbar_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            search_frame,
            text="🔍 Buscar:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="Digite nome, produto, EAN ou código...",
            width=400,
            height=35
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_change)

        ctk.CTkButton(
            search_frame,
            text="🔍 Buscar",
            command=self.search_products,
            width=100,
            height=35
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            search_frame,
            text="🔄 Limpar",
            command=self.clear_search,
            width=100,
            height=35
        ).pack(side="left")

        # Linha 2: Ações
        actions_frame = ctk.CTkFrame(toolbar_frame, fg_color="transparent")
        actions_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            actions_frame,
            text="➕ Novo Produto",
            command=self.add_product_dialog,
            height=35,
            width=140
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions_frame,
            text="✏️ Editar",
            command=self.edit_product_dialog,
            height=35,
            width=120
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions_frame,
            text="🗑️ Excluir",
            command=self.delete_product,
            height=35,
            width=120
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions_frame,
            text="📋 Duplicar",
            command=self.duplicate_product,
            height=35,
            width=120
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            actions_frame,
            text="🔄 Atualizar",
            command=self.refresh_data,
            height=35,
            width=120
        ).pack(side="left")

        # Filtros rápidos
        filters_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        filters_frame.pack(side="right")

        ctk.CTkLabel(
            filters_frame,
            text="Filtros:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.filter_var = tk.StringVar(value="Todos")
        self.filter_combo = ctk.CTkComboBox(
            filters_frame,
            variable=self.filter_var,
            values=["Todos", "Com EAN", "Sem EAN", "Ativos", "Inativos"],
            command=self.on_filter_change,
            width=120
        )
        self.filter_combo.pack(side="left")

    def create_products_list(self, parent):
        """Cria lista de produtos"""
        list_frame = ctk.CTkFrame(parent)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # ✅ TODAS AS 13 COLUNAS DA IMAGEM
        columns = (
            "ID", "COD AUXILIAR", "COD BARRA", "COD FABRIC", "MARCA",
            "DISPONÍVEL", "PREÇO", "PROMOÇÃO", "COMPLEMENTO", "CATEGORIA",
            "ESTOQUE SEG", "CUSTO TOTAL", "DIAS P/ ENTREGA", "SITE_DISPONIBILIDADE", "Status"
        )
        self.products_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=20
        )

        # ✅ CONFIGURAR TODAS AS COLUNAS
        column_configs = {
            "ID": (60, "center"),
            "COD AUXILIAR": (120, "center"),
            "COD BARRA": (130, "center"),
            "COD FABRIC": (120, "center"),
            "MARCA": (100, "w"),
            "DISPONÍVEL": (90, "center"),
            "PREÇO": (80, "center"),
            "PROMOÇÃO": (90, "center"),
            "COMPLEMENTO": (150, "w"),
            "CATEGORIA": (120, "w"),
            "ESTOQUE SEG": (100, "center"),
            "CUSTO TOTAL": (100, "center"),
            "DIAS P/ ENTREGA": (120, "center"),
            "SITE_DISPONIBILIDADE": (150, "center"),
            "Status": (80, "center")
        }

        for col, (width, anchor) in column_configs.items():
            self.products_tree.heading(col, text=col)
            self.products_tree.column(col, width=width, anchor=anchor)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.products_tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient="horizontal", command=self.products_tree.xview)
        self.products_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Pack treeview e scrollbars
        self.products_tree.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        v_scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)
        h_scrollbar.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        # Bind de seleção e duplo clique
        self.products_tree.bind("<<TreeviewSelect>>", self.on_product_select)
        self.products_tree.bind("<Double-1>", lambda e: self.edit_product_dialog())

    def update_products_list(self):
        """Atualiza lista de produtos"""
        try:
            # Limpar lista
            for item in self.products_tree.get_children():
                self.products_tree.delete(item)

            # ✅ ADICIONAR PRODUTOS COM TODAS AS 13 COLUNAS
            for produto in self.produtos_data:
                values = (
                    produto.id,
                    produto.cod_auxiliar,
                    produto.cod_barra,
                    produto.cod_fabric,
                    produto.marca,
                    produto.disponivel,
                    produto.preco,
                    produto.promocao,
                    produto.complemento[:20] + "..." if len(produto.complemento) > 20 else produto.complemento,
                    produto.categoria[:15] + "..." if len(produto.categoria) > 15 else produto.categoria,
                    produto.estoque_seg,
                    produto.custo_total,
                    produto.dias_p_entrega,
                    produto.site_disponibilidade[:20] + "..." if len(
                        produto.site_disponibilidade) > 20 else produto.site_disponibilidade,
                    produto.status
                )
                self.products_tree.insert("", "end", values=values)

        except Exception as e:
            logger.error(f"Erro ao atualizar lista: {e}")
            messagebox.showerror("Erro", f"Erro ao atualizar lista:\n{e}")

    def create_pagination(self, parent):
        """Cria controles de paginação"""
        pagination_frame = ctk.CTkFrame(parent)
        pagination_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Info da página
        self.page_info_var = tk.StringVar(value="Página 1 de 1 (0 itens)")
        page_info_label = ctk.CTkLabel(
            pagination_frame,
            textvariable=self.page_info_var,
            font=ctk.CTkFont(size=12)
        )
        page_info_label.pack(side="left", padx=(20, 0), pady=15)

        # Controles de página
        page_controls = ctk.CTkFrame(pagination_frame, fg_color="transparent")
        page_controls.pack(side="right", padx=(0, 20), pady=15)

        ctk.CTkButton(
            page_controls,
            text="⏮️ Primeira",
            command=self.first_page,
            width=80,
            height=30
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            page_controls,
            text="◀️ Anterior",
            command=self.prev_page,
            width=80,
            height=30
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            page_controls,
            text="▶️ Próxima",
            command=self.next_page,
            width=80,
            height=30
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            page_controls,
            text="⏭️ Última",
            command=self.last_page,
            width=80,
            height=30
        ).pack(side="left")

        # Seletor de itens por página
        items_frame = ctk.CTkFrame(page_controls, fg_color="transparent")
        items_frame.pack(side="left", padx=(20, 0))

        ctk.CTkLabel(
            items_frame,
            text="Itens por página:",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(0, 5))

        self.items_per_page_var = tk.StringVar(value="100")
        items_combo = ctk.CTkComboBox(
            items_frame,
            variable=self.items_per_page_var,
            values=["50", "100", "200", "500"],
            command=self.on_items_per_page_change,
            width=80
        )
        items_combo.pack(side="left")

    def create_search_tab(self):
        """Cria aba de busca avançada"""
        search_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(search_frame, text="🔍 Busca Avançada")

        # Título
        title_label = ctk.CTkLabel(
            search_frame,
            text="🔍 Busca Avançada de Produtos",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(30, 20))

        # Formulário de busca
        form_frame = ctk.CTkFrame(search_frame)
        form_frame.pack(fill="x", padx=50, pady=(0, 20))

        # Criar campos de busca
        self.create_search_fields(form_frame)

        # Resultados da busca
        results_frame = ctk.CTkFrame(search_frame)
        results_frame.pack(fill="both", expand=True, padx=50, pady=(0, 30))

        ctk.CTkLabel(
            results_frame,
            text="📋 Resultados da Busca:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Lista de resultados (simplificada)
        self.search_results_tree = ttk.Treeview(
            results_frame,
            columns=("Nome", "Produto", "EAN", "Tipo"),
            show="headings",
            height=15
        )

        for col in ["Nome", "Produto", "EAN", "Tipo"]:
            self.search_results_tree.heading(col, text=col)
            self.search_results_tree.column(col, width=200)

        search_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.search_results_tree.yview)
        self.search_results_tree.configure(yscrollcommand=search_scrollbar.set)

        self.search_results_tree.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=(0, 20))
        search_scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=(0, 20))

    def create_search_fields(self, parent):
        """Cria campos de busca avançada"""
        # Grid de campos
        fields_frame = ctk.CTkFrame(parent, fg_color="transparent")
        fields_frame.pack(fill="x", padx=20, pady=20)

        # Primeira linha
        row1 = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 15))

        # Nome D'Rossi
        ctk.CTkLabel(row1, text="Nome D'Rossi:", width=120).pack(side="left", padx=(0, 10))
        self.search_nome_var = tk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.search_nome_var, width=200).pack(side="left", padx=(0, 20))

        # Produto
        ctk.CTkLabel(row1, text="Produto:", width=80).pack(side="left", padx=(0, 10))
        self.search_produto_var = tk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.search_produto_var, width=200).pack(side="left")

        # Segunda linha
        row2 = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 15))

        # EAN
        ctk.CTkLabel(row2, text="EAN:", width=120).pack(side="left", padx=(0, 10))
        self.search_ean_var = tk.StringVar()
        ctk.CTkEntry(row2, textvariable=self.search_ean_var, width=200).pack(side="left", padx=(0, 20))

        # Código Fornecedor
        ctk.CTkLabel(row2, text="Cód. Fornecedor:", width=80).pack(side="left", padx=(0, 10))
        self.search_cod_var = tk.StringVar()
        ctk.CTkEntry(row2, textvariable=self.search_cod_var, width=200).pack(side="left")

        # Terceira linha
        row3 = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row3.pack(fill="x", pady=(0, 15))

        # Tipo Produto
        ctk.CTkLabel(row3, text="Tipo Produto:", width=120).pack(side="left", padx=(0, 10))
        self.search_tipo_var = tk.StringVar()
        ctk.CTkEntry(row3, textvariable=self.search_tipo_var, width=200).pack(side="left", padx=(0, 20))

        # Tecido
        ctk.CTkLabel(row3, text="Tecido:", width=80).pack(side="left", padx=(0, 10))
        self.search_tecido_var = tk.StringVar()
        ctk.CTkEntry(row3, textvariable=self.search_tecido_var, width=200).pack(side="left")

        # Botões de busca
        buttons_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            buttons_frame,
            text="🔍 Buscar",
            command=self.advanced_search,
            width=120,
            height=35
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            buttons_frame,
            text="🔄 Limpar",
            command=self.clear_advanced_search,
            width=120,
            height=35
        ).pack(side="left")

    def create_stats_tab(self):
        """Cria aba de estatísticas"""
        stats_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(stats_frame, text="📊 Estatísticas")

        # Título
        title_label = ctk.CTkLabel(
            stats_frame,
            text="📊 Estatísticas do Catálogo",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(30, 20))

        # Container para estatísticas
        self.stats_container = ctk.CTkFrame(stats_frame)
        self.stats_container.pack(fill="both", expand=True, padx=50, pady=(0, 30))

        # Botão para atualizar estatísticas
        ctk.CTkButton(
            stats_frame,
            text="🔄 Atualizar Estatísticas",
            command=self.update_stats,
            width=180,
            height=35
        ).pack(pady=(0, 30))

    def create_bottom_buttons(self, parent):
        """Cria botões inferiores"""
        bottom_frame = ctk.CTkFrame(parent)
        bottom_frame.pack(fill="x", padx=20, pady=(0, 20))

        buttons_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        buttons_frame.pack(expand=True, pady=15)

        # Estatísticas rápidas
        self.quick_stats_var = tk.StringVar(value="📊 Carregando estatísticas...")
        stats_label = ctk.CTkLabel(
            buttons_frame,
            textvariable=self.quick_stats_var,
            font=ctk.CTkFont(size=12)
        )
        stats_label.pack(side="left", padx=(0, 20))

        # Botões
        ctk.CTkButton(
            buttons_frame,
            text="📥 Importar Catálogo",
            command=self.import_catalog,
            height=35,
            width=150
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="📊 Exportar Excel",
            command=self.export_catalog,
            height=35,
            width=130
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
        """Carrega dados dos produtos"""
        try:
            # Aplicar filtros
            search_term = self.search_term if hasattr(self, 'search_term') else ""

            # Calcular offset
            offset = self.current_page * self.items_per_page

            # Carregar produtos
            self.produtos_data = self.db.list_produtos(
                limit=self.items_per_page,
                offset=offset,
                search=search_term
            )

            # Atualizar lista
            self.update_products_list()

            # Atualizar paginação
            self.update_pagination_info()

            # Atualizar estatísticas rápidas
            self.update_quick_stats()

        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            messagebox.showerror("Erro", f"Erro ao carregar dados:\n{e}")


    def update_pagination_info(self):
        """Atualiza informações de paginação"""
        try:
            # Contar total de itens (aproximado)
            total_pages = max(1, (self.total_items + self.items_per_page - 1) // self.items_per_page)
            current_page_display = self.current_page + 1

            # Calcular range de itens
            start_item = self.current_page * self.items_per_page + 1
            end_item = min(start_item + len(self.produtos_data) - 1, self.total_items)

            info_text = f"Página {current_page_display} de {total_pages} ({start_item}-{end_item} de {self.total_items} itens)"
            self.page_info_var.set(info_text)

        except Exception as e:
            logger.error(f"Erro ao atualizar paginação: {e}")

    def update_quick_stats(self):
        """Atualiza estatísticas rápidas"""
        try:
            stats = self.db.get_stats()
            stats_text = (
                f"📦 Total: {stats.get('total_produtos', 0)} | "
                f"✅ Com EAN: {stats.get('com_ean', 0)} | "
                f"❌ Sem EAN: {stats.get('sem_ean', 0)}"
            )
            self.quick_stats_var.set(stats_text)

            # Atualizar total de itens para paginação
            self.total_items = stats.get('total_produtos', 0)

        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas: {e}")

    # EVENTOS
    def on_product_select(self, event):
        """Evento de seleção de produto"""
        selection = self.products_tree.selection()
        if selection:
            item = self.products_tree.item(selection[0])
            produto_id = item['values'][0]
            self.selected_produto = next((p for p in self.produtos_data if p.id == produto_id), None)

    def on_search_change(self, event):
        """Evento de mudança na busca"""
        # Implementar busca com delay para evitar muitas consultas
        if hasattr(self, '_search_timer'):
            self.window.after_cancel(self._search_timer)

        self._search_timer = self.window.after(500, self.search_products)

    def on_filter_change(self, value):
        """Evento de mudança no filtro"""
        # Implementar filtros específicos
        self.current_page = 0
        self.load_data()

    def on_items_per_page_change(self, value):
        """Evento de mudança na quantidade de itens por página"""
        try:
            self.items_per_page = int(value)
            self.current_page = 0
            self.load_data()
        except:
            pass

    # AÇÕES
    def search_products(self):
        """Busca produtos"""
        self.search_term = self.search_var.get().strip()
        self.current_page = 0
        self.load_data()

    def clear_search(self):
        """Limpa busca"""
        self.search_var.set("")
        self.search_term = ""
        self.current_page = 0
        self.load_data()

    def advanced_search(self):
        """Busca avançada"""
        try:
            # Construir filtros
            filters = {}

            if self.search_produto_var.get().strip():
                filters['produto'] = self.search_produto_var.get().strip()

            if self.search_ean_var.get().strip():
                filters['ean_variacao'] = self.search_ean_var.get().strip()

            if self.search_cod_var.get().strip():
                filters['cod_fornecedor'] = self.search_cod_var.get().strip()

            if self.search_tipo_var.get().strip():
                filters['tipo_produto'] = self.search_tipo_var.get().strip()

            if self.search_tecido_var.get().strip():
                filters['tecido'] = self.search_tecido_var.get().strip()

            # Executar busca
            results = self.db.search_produtos(**filters)

            # Atualizar resultados
            for item in self.search_results_tree.get_children():
                self.search_results_tree.delete(item)

            for produto in results:
                self.search_results_tree.insert("", "end", values=(
                    produto.produto[:30],
                    produto.ean_variacao,
                    produto.tipo_produto
                ))

            messagebox.showinfo("Busca", f"Encontrados {len(results)} produtos")

        except Exception as e:
            logger.error(f"Erro na busca avançada: {e}")
            messagebox.showerror("Erro", f"Erro na busca:\n{e}")

    def clear_advanced_search(self):
        """Limpa busca avançada"""
        self.search_nome_var.set("")
        self.search_produto_var.set("")
        self.search_ean_var.set("")
        self.search_cod_var.set("")
        self.search_tipo_var.set("")
        self.search_tecido_var.set("")

        # Limpar resultados
        for item in self.search_results_tree.get_children():
            self.search_results_tree.delete(item)

    # PAGINAÇÃO
    def first_page(self):
        """Primeira página"""
        self.current_page = 0
        self.load_data()

    def prev_page(self):
        """Página anterior"""
        if self.current_page > 0:
            self.current_page -= 1
            self.load_data()

    def next_page(self):
        """Próxima página"""
        max_page = max(0, (self.total_items - 1) // self.items_per_page)
        if self.current_page < max_page:
            self.current_page += 1
            self.load_data()

    def last_page(self):
        """Última página"""
        self.current_page = max(0, (self.total_items - 1) // self.items_per_page)
        self.load_data()

    def refresh_data(self):
        """Atualiza dados"""
        self.load_data()

    # CRUD OPERATIONS (continuarei na próxima parte...)
    def add_product_dialog(self):
        """Diálogo para adicionar produto"""
        messagebox.showinfo("Info", "Funcionalidade de adição será implementada")

    def edit_product_dialog(self):
        """Diálogo para editar produto"""
        if not self.selected_produto:
            messagebox.showwarning("Aviso", "Selecione um produto para editar")
            return

    def delete_product(self):
        """Exclui produto selecionado"""
        if not self.selected_produto:
            messagebox.showwarning("Aviso", "Selecione um produto para excluir")
            return

        response = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o produto:\n\n"
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

    def duplicate_product(self):
        """Duplica produto selecionado"""
        if not self.selected_produto:
            messagebox.showwarning("Aviso", "Selecione um produto para duplicar")
            return

        messagebox.showinfo("Info", "Funcionalidade de duplicação será implementada")

    def update_stats(self):
        """Atualiza estatísticas detalhadas"""
        try:
            # Limpar container
            for widget in self.stats_container.winfo_children():
                widget.destroy()

            # Obter estatísticas
            stats = self.db.get_stats()

            # Criar widgets de estatísticas
            self.create_stats_widgets(self.stats_container, stats)

        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas: {e}")
            messagebox.showerror("Erro", f"Erro ao atualizar estatísticas:\n{e}")

    def create_stats_widgets(self, parent, stats):
        """Cria widgets de estatísticas"""
        # Grid de estatísticas
        stats_grid = ctk.CTkFrame(parent, fg_color="transparent")
        stats_grid.pack(fill="both", expand=True, padx=20, pady=20)

        # Estatísticas gerais
        general_frame = ctk.CTkFrame(stats_grid)
        general_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            general_frame,
            text="📊 Estatísticas Gerais",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(20, 15))

        general_text = f"""
📦 Total de Produtos: {stats.get('total_produtos', 0)}
✅ Produtos com EAN: {stats.get('com_ean', 0)}
❌ Produtos sem EAN: {stats.get('sem_ean', 0)}
"""

        ctk.CTkLabel(
            general_frame,
            text=general_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(pady=(0, 20))

        # Estatísticas por tipo
        if stats.get('por_tipo'):
            tipo_frame = ctk.CTkFrame(stats_grid)
            tipo_frame.pack(fill="x", pady=(0, 20))

            ctk.CTkLabel(
                tipo_frame,
                text="��️ Por Tipo de Produto",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 15))

            tipo_text = "\n".join([f"• {tipo}: {count}" for tipo, count in stats['por_tipo'].items()])

            ctk.CTkLabel(
                tipo_frame,
                text=tipo_text,
                font=ctk.CTkFont(size=12),
                justify="left"
            ).pack(pady=(0, 20))

    def import_catalog(self):
        """Importa catálogo"""
        try:
            # Import local para evitar problemas de dependência circular
            from .catalog_import_dialog import CatalogImportDialog

            # ✅ CORREÇÃO: Usar self.db que já está inicializado
            dialog = CatalogImportDialog(self.window, self.db)
            self.window.wait_window(dialog.dialog)

            if dialog.result == "success":
                self.load_data()  # ✅ Recarregar dados após importação

        except Exception as e:
            logger.error(f"Erro ao abrir importador: {e}")
            messagebox.showerror("Erro", f"Erro ao abrir importador:\n{e}")

    def create_edit_form(self, parent, produto: Optional[ProdutoCatalogo] = None):
        """Cria formulário de edição de produto"""
        # Frame principal do formulário
        form_frame = ctk.CTkScrollableFrame(parent)
        form_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Variáveis do formulário
        self.form_vars = {}

        # ✅ TODOS OS 13 CAMPOS
        fields = [
            ("COD AUXILIAR", "cod_auxiliar"),
            ("COD BARRA", "cod_barra"),
            ("COD FABRIC", "cod_fabric"),
            ("MARCA", "marca"),
            ("DISPONÍVEL", "disponivel"),
            ("PREÇO", "preco"),
            ("PROMOÇÃO", "promocao"),
            ("COMPLEMENTO", "complemento"),
            ("CATEGORIA", "categoria"),
            ("ESTOQUE SEG", "estoque_seg"),
            ("CUSTO TOTAL", "custo_total"),
            ("DIAS P/ ENTREGA", "dias_p_entrega"),
            ("SITE_DISPONIBILIDADE", "site_disponibilidade")
        ]

        # Criar campos do formulário
        for i, (label_text, field_name) in enumerate(fields):
            # Frame para cada campo
            field_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
            field_frame.pack(fill="x", pady=5)

            # Label
            label = ctk.CTkLabel(
                field_frame,
                text=f"{label_text}:",
                font=ctk.CTkFont(size=12, weight="bold"),
                width=150
            )
            label.pack(side="left", padx=(0, 10))

            # Entry
            var = tk.StringVar()
            if produto:
                var.set(getattr(produto, field_name, ""))

            entry = ctk.CTkEntry(
                field_frame,
                textvariable=var,
                height=30
            )
            entry.pack(side="left", fill="x", expand=True)

            self.form_vars[field_name] = var

        return form_frame

    def export_catalog(self):
        """Exporta catálogo"""
        messagebox.showinfo("Info", "Funcionalidade de exportação será implementada")

    def on_closing(self):
        """Fecha a janela"""
        self.window.destroy()