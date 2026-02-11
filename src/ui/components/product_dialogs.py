"""Diálogos para edição de produtos e componentes"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class ProductEditDialog:
    """Diálogo para editar produto"""

    def __init__(self, parent, title: str, produto_data: Optional[Dict] = None):
        self.result = None
        self.produto_data = produto_data or {}

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Criar widgets
        self.create_widgets()

        # Preencher dados se for edição
        if self.produto_data:
            self.fill_data()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 500) // 2
        y = (self.dialog.winfo_screenheight() - 300) // 2
        self.dialog.geometry(f"500x300+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets do diálogo"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_text = "Editar Produto" if self.produto_data else "Novo Produto"
        title_label = ctk.CTkLabel(
            main_frame,
            text=title_text,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Campo Nome da Aba
        ctk.CTkLabel(
            main_frame,
            text="Nome da Aba (Produto):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(0, 5))

        self.nome_var = tk.StringVar()
        self.nome_entry = ctk.CTkEntry(
            main_frame,
            textvariable=self.nome_var,
            placeholder_text="Ex: Alice, Aline, Anitta...",
            font=ctk.CTkFont(size=12),
            height=35
        )
        self.nome_entry.pack(fill="x", padx=20, pady=(0, 20))

        # Campo Status (apenas para edição)
        if self.produto_data:
            ctk.CTkLabel(
                main_frame,
                text="Status:",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=20, pady=(0, 5))

            self.status_var = tk.StringVar(value="Ativo")
            self.status_combo = ctk.CTkComboBox(
                main_frame,
                variable=self.status_var,
                values=["Ativo", "Inativo"],
                height=35
            )
            self.status_combo.pack(fill="x", padx=20, pady=(0, 20))

        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(20, 20))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="✅ Salvar",
            command=self.save,
            width=120,
            height=35
        ).pack(side="right")

        # Binds
        self.nome_entry.focus()
        self.nome_entry.bind("<Return>", lambda e: self.save())
        self.dialog.bind("<Escape>", lambda e: self.cancel())

    def fill_data(self):
        """Preenche dados para edição"""
        self.nome_var.set(self.produto_data.get("nome_aba", ""))
        if hasattr(self, 'status_var'):
            self.status_var.set(self.produto_data.get("status", "Ativo"))

    def save(self):
        """Salva os dados"""
        nome = self.nome_var.get().strip()
        if not nome:
            messagebox.showwarning("Aviso", "Digite o nome da aba")
            self.nome_entry.focus()
            return

        self.result = {
            "nome_aba": nome,
            "status": getattr(self, 'status_var', tk.StringVar(value="Ativo")).get()
        }

        self.dialog.destroy()

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()


class AssentoEditDialog:
    """Diálogo para editar assento"""

    def __init__(self, parent, title: str, assento_data: Optional[Dict] = None):
        self.result = None
        self.assento_data = assento_data or {}

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Criar widgets
        self.create_widgets()

        # Preencher dados se for edição
        if self.assento_data:
            self.fill_data()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 600) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"600x500+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets do diálogo"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_text = "Editar Assento" if self.assento_data else "Novo Assento"
        title_label = ctk.CTkLabel(
            main_frame,
            text=title_text,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Campos
        fields = [
            ("Nome:", "nome", "Ex: Assento Poltrona"),
            ("Modelo:", "modelo", "Ex: Alice, Aline, Anitta"),
            ("Revestimento:", "revestimento", "Ex: Suede Azul Marinho, Veludo Bege"),
            ("Código EAN:", "ean", "Ex: 7891234567890"),
            ("Código Interno:", "codigo", "Ex: ASS001")
        ]

        self.vars = {}

        for label_text, var_name, placeholder in fields:
            # Label
            ctk.CTkLabel(
                main_frame,
                text=label_text,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=20, pady=(10, 5))

            # Entry
            self.vars[var_name] = tk.StringVar()
            entry = ctk.CTkEntry(
                main_frame,
                textvariable=self.vars[var_name],
                placeholder_text=placeholder,
                font=ctk.CTkFont(size=12),
                height=35
            )
            entry.pack(fill="x", padx=20, pady=(0, 10))

        # Status (apenas para edição)
        if self.assento_data:
            ctk.CTkLabel(
                main_frame,
                text="Status:",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=20, pady=(10, 5))

            self.vars["status"] = tk.StringVar(value="Ativo")
            self.status_combo = ctk.CTkComboBox(
                main_frame,
                variable=self.vars["status"],
                values=["Ativo", "Inativo"],
                height=35
            )
            self.status_combo.pack(fill="x", padx=20, pady=(0, 20))

        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(20, 20))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="✅ Salvar",
            command=self.save,
            width=120,
            height=35
        ).pack(side="right")

        # Focus no primeiro campo
        list(self.vars.values())[0].get()  # Trigger para criar entry
        self.dialog.bind("<Escape>", lambda e: self.cancel())

    def fill_data(self):
        """Preenche dados para edição"""
        for key, var in self.vars.items():
            if key in self.assento_data:
                var.set(str(self.assento_data[key]))

    def save(self):
        """Salva os dados"""
        # Validar campos obrigatórios
        if not self.vars["modelo"].get().strip():
            messagebox.showwarning("Aviso", "Digite o modelo do assento")
            return

        if not self.vars["revestimento"].get().strip():
            messagebox.showwarning("Aviso", "Digite o revestimento do assento")
            return

        # Preparar resultado
        self.result = {}
        for key, var in self.vars.items():
            self.result[key] = var.get().strip()

        # Valores padrão
        if not self.result["nome"]:
            self.result["nome"] = "Assento"

        if "status" not in self.result:
            self.result["status"] = "Ativo"

        self.dialog.destroy()

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()


class PeBaseEditDialog:
    """Diálogo para editar pé/base"""

    def __init__(self, parent, title: str, pe_base_data: Optional[Dict] = None):
        self.result = None
        self.pe_base_data = pe_base_data or {}

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("600x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Criar widgets
        self.create_widgets()

        # Preencher dados se for edição
        if self.pe_base_data:
            self.fill_data()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 600) // 2
        y = (self.dialog.winfo_screenheight() - 400) // 2
        self.dialog.geometry(f"600x400+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets do diálogo"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_text = "Editar Pé/Base" if self.pe_base_data else "Novo Pé/Base"
        title_label = ctk.CTkLabel(
            main_frame,
            text=title_text,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Campos
        fields = [
            ("Nome:", "nome", "Ex: Pés Palito Natural, Base Giratória MA30"),
            ("Código EAN:", "ean", "Ex: 7891234567890"),
            ("Código Interno:", "codigo", "Ex: PE001, BASE001")
        ]

        self.vars = {}

        for label_text, var_name, placeholder in fields:
            # Label
            ctk.CTkLabel(
                main_frame,
                text=label_text,
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=20, pady=(10, 5))

            # Entry
            self.vars[var_name] = tk.StringVar()
            entry = ctk.CTkEntry(
                main_frame,
                textvariable=self.vars[var_name],
                placeholder_text=placeholder,
                font=ctk.CTkFont(size=12),
                height=35
            )
            entry.pack(fill="x", padx=20, pady=(0, 10))

        # Quantidade
        ctk.CTkLabel(
            main_frame,
            text="Quantidade:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(10, 5))

        self.vars["quantidade"] = tk.StringVar(value="1")
        quantidade_entry = ctk.CTkEntry(
            main_frame,
            textvariable=self.vars["quantidade"],
            placeholder_text="Ex: 1 (para base), 4 (para pés)",
            font=ctk.CTkFont(size=12),
            height=35
        )
        quantidade_entry.pack(fill="x", padx=20, pady=(0, 10))

        # Status (apenas para edição)
        if self.pe_base_data:
            ctk.CTkLabel(
                main_frame,
                text="Status:",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=20, pady=(10, 5))

            self.vars["status"] = tk.StringVar(value="Ativo")
            self.status_combo = ctk.CTkComboBox(
                main_frame,
                variable=self.vars["status"],
                values=["Ativo", "Inativo"],
                height=35
            )
            self.status_combo.pack(fill="x", padx=20, pady=(0, 20))

        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(20, 20))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="✅ Salvar",
            command=self.save,
            width=120,
            height=35
        ).pack(side="right")

        # Binds
        self.dialog.bind("<Escape>", lambda e: self.cancel())

    def fill_data(self):
        """Preenche dados para edição"""
        for key, var in self.vars.items():
            if key in self.pe_base_data:
                var.set(str(self.pe_base_data[key]))

    def save(self):
        """Salva os dados"""
        # Validar campos obrigatórios
        if not self.vars["nome"].get().strip():
            messagebox.showwarning("Aviso", "Digite o nome do pé/base")
            return

        # Validar quantidade
        try:
            quantidade = int(self.vars["quantidade"].get().strip() or "1")
            if quantidade <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Aviso", "Digite uma quantidade válida (número inteiro positivo)")
            return

        # Preparar resultado
        self.result = {}
        for key, var in self.vars.items():
            if key == "quantidade":
                self.result[key] = quantidade
            else:
                self.result[key] = var.get().strip()

        # Valores padrão
        if "status" not in self.result:
            self.result["status"] = "Ativo"

        self.dialog.destroy()

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()


class CombinationDialog:
    """Diálogo para criar combinação manual"""

    def __init__(self, parent, db, produto_id: int):
        self.result = None
        self.db = db
        self.produto_id = produto_id

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("Nova Combinação")
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Carregar dados
        self.load_data()

        # Criar widgets
        self.create_widgets()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 500) // 2
        y = (self.dialog.winfo_screenheight() - 400) // 2
        self.dialog.geometry(f"500x400+{x}+{y}")

    def load_data(self):
        """Carrega assentos e pés/bases do produto"""
        self.assentos = self.db.list_assentos_by_produto(self.produto_id)
        self.pes_bases = self.db.list_pes_bases_by_produto(self.produto_id)

    def create_widgets(self):
        """Cria os widgets do diálogo"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="Nova Combinação",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Verificar se há dados
        if not self.assentos:
            ctk.CTkLabel(
                main_frame,
                text="❌ Nenhum assento encontrado para este produto",
                font=ctk.CTkFont(size=14),
                text_color="red"
            ).pack(pady=20)

            ctk.CTkButton(
                main_frame,
                text="Fechar",
                command=self.cancel,
                width=120
            ).pack(pady=20)
            return

        if not self.pes_bases:
            ctk.CTkLabel(
                main_frame,
                text="❌ Nenhum pé/base encontrado para este produto",
                font=ctk.CTkFont(size=14),
                text_color="red"
            ).pack(pady=20)

            ctk.CTkButton(
                main_frame,
                text="Fechar",
                command=self.cancel,
                width=120
            ).pack(pady=20)
            return

        # Seleção de assento
        ctk.CTkLabel(
            main_frame,
            text="Selecione o Assento:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(0, 5))

        assento_values = [f"{a.modelo} - {a.revestimento}" for a in self.assentos]
        self.assento_var = tk.StringVar()
        self.assento_combo = ctk.CTkComboBox(
            main_frame,
            variable=self.assento_var,
            values=assento_values,
            height=35
        )
        self.assento_combo.pack(fill="x", padx=20, pady=(0, 20))

        # Seleção de pé/base
        ctk.CTkLabel(
            main_frame,
            text="Selecione o Pé/Base:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(0, 5))

        pe_values = [f"{p.nome} (Qtd: {p.quantidade})" for p in self.pes_bases]
        self.pe_var = tk.StringVar()
        self.pe_combo = ctk.CTkComboBox(
            main_frame,
            variable=self.pe_var,
            values=pe_values,
            height=35
        )
        self.pe_combo.pack(fill="x", padx=20, pady=(0, 30))

        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(20, 20))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="✅ Criar Combinação",
            command=self.save,
            width=150,
            height=35
        ).pack(side="right")

    def save(self):
        """Salva a combinação"""
        assento_index = self.assento_combo.current()
        pe_index = self.pe_combo.current()

        if assento_index < 0:
            messagebox.showwarning("Aviso", "Selecione um assento")
            return

        if pe_index < 0:
            messagebox.showwarning("Aviso", "Selecione um pé/base")
            return

        self.result = {
            "assento_id": self.assentos[assento_index].id,
            "pe_base_id": self.pes_bases[pe_index].id,
            "produto_id": self.produto_id
        }

        self.dialog.destroy()

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()