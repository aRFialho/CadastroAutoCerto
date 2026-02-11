"""Interface para gerenciamento de categorias da Loja Web"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Optional
import json

from ...services.category_manager import CategoryManager
from ...core.models import CategoryItem
from ...utils.logger import get_logger

logger = get_logger("category_manager_window")


class CategoryManagerWindow:
    """Janela de gerenciamento de categorias"""

    def __init__(self, parent, category_manager: CategoryManager):
        self.parent = parent
        self.category_manager = category_manager
        self.selected_category_id = None

        self.setup_window()
        self.create_widgets()
        self.refresh_tree()

    def setup_window(self):
        """Configura a janela principal"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("🏷️ Gerenciador de Categorias da Loja Web")
        self.window.geometry("1200x800")
        self.window.minsize(1000, 700)

        # Centralizar janela
        self.window.transient(self.parent)
        self.window.grab_set()

        # Protocolo de fechamento
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Header
        self.create_header()

        # Main content
        self.create_main_content()

        # Footer
        self.create_footer()

    def create_header(self):
        """Cria o cabeçalho"""
        header_frame = ctk.CTkFrame(self.window, height=80)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        # Título
        title_label = ctk.CTkLabel(
            header_frame,
            text="🏷️ Gerenciador de Categorias da Loja Web",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(expand=True)

    def create_main_content(self):
        """Cria o conteúdo principal"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Dividir em duas colunas
        # Coluna esquerda: Árvore de categorias
        left_frame = ctk.CTkFrame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(20, 10), pady=20)

        # Coluna direita: Controles
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.pack(side="right", fill="y", padx=(10, 20), pady=20)

        self.create_tree_section(left_frame)
        self.create_controls_section(right_frame)

    def create_tree_section(self, parent):
        """Cria a seção da árvore de categorias"""
        # Título da seção
        tree_title = ctk.CTkLabel(
            parent,
            text="📋 Estrutura de Categorias",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        tree_title.pack(pady=(20, 15))

        # Frame para busca
        search_frame = ctk.CTkFrame(parent, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search_change)

        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="🔍 Buscar categoria...",
            height=35
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        clear_search_btn = ctk.CTkButton(
            search_frame,
            text="✖️",
            command=self.clear_search,
            width=40,
            height=35
        )
        clear_search_btn.pack(side="right")

        # Frame para a árvore com scrollbar
        tree_container = ctk.CTkFrame(parent)
        tree_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Criar Treeview usando tkinter nativo (CustomTkinter não tem TreeView)
        import tkinter.ttk as ttk

        # Frame para o treeview
        tree_frame = tk.Frame(tree_container, bg="#212121")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Treeview
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("status", "id"),
            show="tree headings",
            height=20
        )

        # Configurar colunas
        self.tree.heading("#0", text="Categoria", anchor="w")
        self.tree.heading("status", text="Status", anchor="center")
        self.tree.heading("id", text="ID", anchor="center")

        self.tree.column("#0", width=300, minwidth=200)
        self.tree.column("status", width=80, minwidth=60)
        self.tree.column("id", width=60, minwidth=40)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)

        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Pack treeview e scrollbars
        self.tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")

        # Bind eventos
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Configurar cores do tema escuro
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        fieldbackground="#2b2b2b",
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background="#1f538d",
                        foreground="white",
                        borderwidth=1)

    def create_controls_section(self, parent):
        """Cria a seção de controles"""
        # Título
        controls_title = ctk.CTkLabel(
            parent,
            text="⚙️ Controles",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        controls_title.pack(pady=(20, 20))

        # Informações da categoria selecionada
        info_frame = ctk.CTkFrame(parent)
        info_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            info_frame,
            text="📋 Categoria Selecionada:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 5))

        self.selected_info_var = tk.StringVar(value="Nenhuma categoria selecionada")
        self.selected_info_label = ctk.CTkLabel(
            info_frame,
            textvariable=self.selected_info_var,
            font=ctk.CTkFont(size=12),
            wraplength=200,
            justify="left"
        )
        self.selected_info_label.pack(pady=(0, 15))

        # Botões de ação
        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20)

        # Adicionar categoria raiz
        self.add_root_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Adicionar Categoria Raiz",
            command=self.add_root_category,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.add_root_btn.pack(fill="x", pady=(0, 10))

        # Adicionar subcategoria
        self.add_sub_btn = ctk.CTkButton(
            buttons_frame,
            text="📁 Adicionar Subcategoria",
            command=self.add_subcategory,
            height=40,
            state="disabled"
        )
        self.add_sub_btn.pack(fill="x", pady=(0, 10))

        # Editar categoria
        self.edit_btn = ctk.CTkButton(
            buttons_frame,
            text="✏️ Editar Nome",
            command=self.edit_category,
            height=40,
            state="disabled"
        )
        self.edit_btn.pack(fill="x", pady=(0, 10))

        # Alternar status
        self.toggle_status_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 Alternar Status",
            command=self.toggle_category_status,
            height=40,
            state="disabled"
        )
        self.toggle_status_btn.pack(fill="x", pady=(0, 20))

        # Separador
        separator = ctk.CTkFrame(buttons_frame, height=2)
        separator.pack(fill="x", pady=(10, 20))

        # Botões de utilitários
        utils_title = ctk.CTkLabel(
            buttons_frame,
            text="🛠️ Utilitários",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        utils_title.pack(pady=(0, 15))

        # Atualizar árvore
        refresh_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 Atualizar",
            command=self.refresh_tree,
            height=35
        )
        refresh_btn.pack(fill="x", pady=(0, 10))

        # Expandir/Colapsar tudo
        expand_frame = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        expand_frame.pack(fill="x", pady=(0, 10))

        expand_btn = ctk.CTkButton(
            expand_frame,
            text="📂 Expandir",
            command=self.expand_all,
            height=35,
            width=90
        )
        expand_btn.pack(side="left", padx=(0, 5))

        collapse_btn = ctk.CTkButton(
            expand_frame,
            text="📁 Colapsar",
            command=self.collapse_all,
            height=35,
            width=90
        )
        collapse_btn.pack(side="right", padx=(5, 0))

        # Exportar/Importar
        export_btn = ctk.CTkButton(
            buttons_frame,
            text="📤 Exportar JSON",
            command=self.export_categories,
            height=35
        )
        export_btn.pack(fill="x", pady=(0, 10))
        # Importar do TXT
        import_btn = ctk.CTkButton(
            buttons_frame,
            text="📥 Importar do TXT",
            command=self.import_from_txt,
            height=35
        )
        import_btn.pack(fill="x", pady=(0, 10))

        # Limpar todas (para reimportação)
        clear_btn = ctk.CTkButton(
            buttons_frame,
            text="🗑️ Limpar Todas",
            command=self.clear_all_categories,
            height=35,
            fg_color=("red", "darkred"),
            hover_color=("darkred", "red")
        )
        clear_btn.pack(fill="x", pady=(0, 10))
        # Estatísticas
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(
            stats_frame,
            text="📊 Estatísticas",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.stats_var = tk.StringVar()
        self.stats_label = ctk.CTkLabel(
            stats_frame,
            textvariable=self.stats_var,
            font=ctk.CTkFont(size=11),
            justify="left"
        )
        self.stats_label.pack(pady=(0, 15))

    def create_footer(self):
        """Cria o rodapé"""
        footer_frame = ctk.CTkFrame(self.window, height=50)
        footer_frame.pack(fill="x", padx=20, pady=(10, 20))
        footer_frame.pack_propagate(False)

        # Botão fechar
        close_btn = ctk.CTkButton(
            footer_frame,
            text="✖️ Fechar",
            command=self.on_closing,
            width=100,
            height=35
        )
        close_btn.pack(side="right", padx=15, pady=8)

        # Info
        info_label = ctk.CTkLabel(
            footer_frame,
            text="💡 Dica: Clique duplo para editar rapidamente",
            font=ctk.CTkFont(size=11),
            text_color=("gray60", "gray40")
        )
        info_label.pack(side="left", padx=15, pady=8)

    def refresh_tree(self):
        """Atualiza a árvore de categorias"""
        try:
            # Limpar árvore
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Recarregar categorias
            self.category_manager.load_categories()
            categories = self.category_manager.get_all_categories()

            # Popular árvore
            for category in categories:
                self._add_category_to_tree(category, "")

            # Atualizar estatísticas
            self.update_statistics()

            logger.info("Árvore de categorias atualizada")

        except Exception as e:
            logger.error(f"Erro ao atualizar árvore: {e}")
            messagebox.showerror("Erro", f"Erro ao atualizar árvore:\n{e}")

    def _add_category_to_tree(self, category: CategoryItem, parent: str):
        """Adiciona categoria à árvore recursivamente"""
        # Ícone baseado no status
        icon = "✅" if category.status == "Ativo" else "❌"

        # Inserir item
        item_id = self.tree.insert(
            parent,
            "end",
            text=f"{icon} {category.name}",
            values=(category.status, category.id),
            tags=(category.status.lower(),)
        )

        # Configurar cores baseadas no status
        if category.status == "Ativo":
            self.tree.set(item_id, "status", "✅ Ativo")
        else:
            self.tree.set(item_id, "status", "❌ Inativo")

        # Adicionar filhos recursivamente
        for child in category.children:
            self._add_category_to_tree(child, item_id)

    def on_tree_select(self, event):
        """Callback quando item da árvore é selecionado"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, "values")

            if values and len(values) >= 2:
                self.selected_category_id = int(values[1])  # ID está na segunda coluna

                # Buscar categoria completa
                category = self.category_manager._find_category_by_id(self.selected_category_id)
                if category:
                    # Atualizar info
                    path = self.category_manager.get_category_path(self.selected_category_id)
                    info_text = f"Nome: {category.name}\nID: {category.id}\nStatus: {category.status}\nCaminho: {path}"
                    self.selected_info_var.set(info_text)

                    # Habilitar botões
                    self.add_sub_btn.configure(state="normal")
                    self.edit_btn.configure(state="normal")
                    self.toggle_status_btn.configure(state="normal")
                else:
                    self.clear_selection()
            else:
                self.clear_selection()
        else:
            self.clear_selection()

    def clear_selection(self):
        """Limpa seleção"""
        self.selected_category_id = None
        self.selected_info_var.set("Nenhuma categoria selecionada")
        self.add_sub_btn.configure(state="disabled")
        self.edit_btn.configure(state="disabled")
        self.toggle_status_btn.configure(state="disabled")

    def on_tree_double_click(self, event):
        """Callback para duplo clique na árvore"""
        if self.selected_category_id:
            self.edit_category()

    def add_root_category(self):
        """Adiciona categoria raiz"""
        self._add_category_dialog(None)

    def add_subcategory(self):
        """Adiciona subcategoria"""
        if self.selected_category_id:
            self._add_category_dialog(self.selected_category_id)
        else:
            messagebox.showwarning("Aviso", "Selecione uma categoria pai primeiro")

    def _add_category_dialog(self, parent_id: Optional[int]):
        """Diálogo para adicionar categoria"""
        # Solicitar nome
        name = simpledialog.askstring(
            "Nova Categoria",
            "Digite o nome da nova categoria:",
            parent=self.window
        )

        if not name or not name.strip():
            return

        # Solicitar senha
        password = simpledialog.askstring(
            "Autenticação",
            "Digite a senha de administrador:",
            parent=self.window,
            show="*"
        )

        if not password:
            return

        # Adicionar categoria
        success, message = self.category_manager.add_category(
            name=name.strip(),
            parent_id=parent_id,
            password=password
        )

        if success:
            messagebox.showinfo("Sucesso", message)
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", message)

    def edit_category(self):
        """Edita categoria selecionada"""
        if not self.selected_category_id:
            messagebox.showwarning("Aviso", "Selecione uma categoria primeiro")
            return

        # Buscar categoria atual
        category = self.category_manager._find_category_by_id(self.selected_category_id)
        if not category:
            messagebox.showerror("Erro", "Categoria não encontrada")
            return

        # Solicitar novo nome
        new_name = simpledialog.askstring(
            "Editar Categoria",
            f"Nome atual: {category.name}\n\nDigite o novo nome:",
            parent=self.window,
            initialvalue=category.name
        )

        if not new_name or not new_name.strip() or new_name.strip() == category.name:
            return

        # Solicitar senha
        password = simpledialog.askstring(
            "Autenticação",
            "Digite a senha de administrador:",
            parent=self.window,
            show="*"
        )

        if not password:
            return

        # Editar categoria
        success, message = self.category_manager.edit_category(
            category_id=self.selected_category_id,
            new_name=new_name.strip(),
            password=password
        )

        if success:
            messagebox.showinfo("Sucesso", message)
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", message)

    def toggle_category_status(self):
        """Alterna status da categoria selecionada"""
        if not self.selected_category_id:
            messagebox.showwarning("Aviso", "Selecione uma categoria primeiro")
            return

        # Buscar categoria atual
        category = self.category_manager._find_category_by_id(self.selected_category_id)
        if not category:
            messagebox.showerror("Erro", "Categoria não encontrada")
            return

        # Confirmar ação
        new_status = "Inativo" if category.status == "Ativo" else "Ativo"
        if not messagebox.askyesno(
                "Confirmar",
                f"Alterar status de '{category.name}' para '{new_status}'?"
        ):
            return

        # Solicitar senha
        password = simpledialog.askstring(
            "Autenticação",
            "Digite a senha de administrador:",
            parent=self.window,
            show="*"
        )

        if not password:
            return

        # Alterar status
        success, message = self.category_manager.toggle_status(
            category_id=self.selected_category_id,
            password=password
        )

        if success:
            messagebox.showinfo("Sucesso", message)
            self.refresh_tree()
        else:
            messagebox.showerror("Erro", message)

    def on_search_change(self, *args):
        """Callback quando busca muda"""
        search_term = self.search_var.get().strip()

        if not search_term:
            self.refresh_tree()
            return

        try:
            # Buscar categorias
            results = self.category_manager.search_categories(search_term)

            # Limpar árvore
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Mostrar resultados
            for category in results:
                path = self.category_manager.get_category_path(category.id)
                icon = "✅" if category.status == "Ativo" else "❌"

                self.tree.insert(
                    "",
                    "end",
                    text=f"{icon} {category.name} ({path})",
                    values=(category.status, category.id)
                )

        except Exception as e:
            logger.error(f"Erro na busca: {e}")

    def clear_search(self):
        """Limpa busca"""
        self.search_var.set("")
        self.refresh_tree()

    def expand_all(self):
        """Expande todos os itens"""

        def expand_recursive(item):
            self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                expand_recursive(child)

        for item in self.tree.get_children():
            expand_recursive(item)

    def collapse_all(self):
        """Colapsa todos os itens"""

        def collapse_recursive(item):
            self.tree.item(item, open=False)
            for child in self.tree.get_children(item):
                collapse_recursive(child)

        for item in self.tree.get_children():
            collapse_recursive(item)

    def export_categories(self):
        """Exporta categorias para JSON"""
        try:
            from tkinter import filedialog

            file_path = filedialog.asksaveasfilename(
                title="Exportar Categorias",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                parent=self.window
            )

            if file_path:
                categories = self.category_manager.get_all_categories()
                data = [self.category_manager._category_to_dict(cat) for cat in categories]

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                messagebox.showinfo("Sucesso", f"Categorias exportadas para:\n{file_path}")

        except Exception as e:
            logger.error(f"Erro ao exportar: {e}")
            messagebox.showerror("Erro", f"Erro ao exportar categorias:\n{e}")

    def update_statistics(self):
        """Atualiza estatísticas"""
        try:
            categories = self.category_manager.get_all_categories()

            def count_recursive(cats):
                total = len(cats)
                active = sum(1 for cat in cats if cat.status == "Ativo")
                for cat in cats:
                    child_total, child_active = count_recursive(cat.children)
                    total += child_total
                    active += child_active
                return total, active

            total_count, active_count = count_recursive(categories)
            inactive_count = total_count - active_count

            stats_text = (
                f"Total: {total_count}\n"
                f"Ativas: {active_count}\n"
                f"Inativas: {inactive_count}"
            )

            self.stats_var.set(stats_text)

        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas: {e}")
            self.stats_var.set("Erro ao calcular")

    def on_closing(self):
        """Callback ao fechar janela"""
        try:
            self.window.destroy()
        except Exception as e:
            logger.error(f"Erro ao fechar janela: {e}")

    # ✅ MOVER ESTES MÉTODOS PARA FORA DO on_closing (MESMO NÍVEL DA CLASSE)
    def import_from_txt(self):
        """Importa categorias de arquivo TXT"""
        try:
            from tkinter import filedialog
            from pathlib import Path  # ✅ ADICIONAR ESTE IMPORT

            # Confirmar ação
            if not messagebox.askyesno(
                    "Confirmar Importação",
                    "⚠️ Esta ação irá SUBSTITUIR todas as categorias atuais!\n\n"
                    "Deseja continuar?\n\n"
                    "💡 Dica: Um backup será criado automaticamente."
            ):
                return

            # Selecionar arquivo
            file_path = filedialog.askopenfilename(
                title="Selecionar Arquivo TXT de Categorias",
                filetypes=[
                    ("Text files", "*.txt"),
                    ("JSON files", "*.json"),
                    ("All files", "*.*")
                ],
                parent=self.window
            )

            if not file_path:
                return

            # Solicitar senha
            password = simpledialog.askstring(
                "Autenticação",
                "Digite a senha de administrador:",
                parent=self.window,
                show="*"
            )

            if not password:
                return

            # Importar
            success, message = self.category_manager.import_from_txt_file(
                txt_file_path=Path(file_path),
                password=password
            )

            if success:
                messagebox.showinfo("Sucesso", message)
                self.refresh_tree()
            else:
                messagebox.showerror("Erro", message)

        except Exception as e:
            logger.error(f"Erro ao importar: {e}")
            messagebox.showerror("Erro", f"Erro ao importar categorias:\n{e}")

    def clear_all_categories(self):
        """Limpa todas as categorias"""
        try:
            # Confirmar ação
            if not messagebox.askyesno(
                    "⚠️ ATENÇÃO - Ação Irreversível!",
                    "�� Esta ação irá REMOVER TODAS as categorias!\n\n"
                    "Esta ação é IRREVERSÍVEL!\n\n"
                    "Tem certeza que deseja continuar?\n\n"
                    "💡 Um backup será criado automaticamente."
            ):
                return

            # Segunda confirmação
            if not messagebox.askyesno(
                    "Confirmação Final",
                    "🔴 ÚLTIMA CHANCE!\n\n"
                    "Confirma que deseja APAGAR TODAS as categorias?\n\n"
                    "Digite 'SIM' para confirmar:",
            ):
                return

            # Solicitar senha
            password = simpledialog.askstring(
                "Autenticação",
                "Digite a senha de administrador:",
                parent=self.window,
                show="*"
            )

            if not password:
                return

            # Limpar
            success, message = self.category_manager.clear_all_categories(password=password)

            if success:
                messagebox.showinfo("Sucesso", message)
                self.refresh_tree()
            else:
                messagebox.showerror("Erro", message)

        except Exception as e:
            logger.error(f"Erro ao limpar: {e}")
            messagebox.showerror("Erro", f"Erro ao limpar categorias:\n{e}")