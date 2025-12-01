"""Diálogo para cadastro/edição de fornecedores"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import logging
from typing import Optional
import json

from ...core.costs_database import CostsDatabase, FornecedorCustos

logger = logging.getLogger(__name__)


class SupplierFormDialog:
    """Diálogo para formulário de fornecedor"""

    def __init__(self, parent, db: CostsDatabase, fornecedor: Optional[FornecedorCustos] = None):
        self.parent = parent
        self.db = db
        self.fornecedor = fornecedor
        self.result = None
        self.is_editing = fornecedor is not None

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        title = "✏️ Editar Fornecedor" if self.is_editing else "➕ Novo Fornecedor"
        self.dialog.title(title)
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Variáveis do formulário
        self.form_vars = {}

        # Criar interface
        self.create_widgets()

        # Preencher dados se editando
        if self.is_editing:
            self.populate_form()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 600) // 2
        y = (self.dialog.winfo_screenheight() - 500) // 2
        self.dialog.geometry(f"600x500+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title = "✏️ Editar Fornecedor" if self.is_editing else "➕ Novo Fornecedor"
        title_label = ctk.CTkLabel(
            main_frame,
            text=title,
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Frame do formulário
        form_frame = ctk.CTkScrollableFrame(main_frame)
        form_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Campos do formulário
        self.create_form_fields(form_frame)

        # Botões
        self.create_buttons(main_frame)

    def create_form_fields(self, parent):
        """Cria campos do formulário"""
        # Informações básicas
        basic_frame = ctk.CTkFrame(parent)
        basic_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            basic_frame,
            text="📋 Informações Básicas",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 15))

        # Nome (obrigatório)
        self.create_field(basic_frame, "Nome *", "nome", required=True)

        # Código
        self.create_field(basic_frame, "Código", "codigo")

        # CNPJ
        self.create_field(basic_frame, "CNPJ", "cnpj")

        # Informações de contato
        contact_frame = ctk.CTkFrame(parent)
        contact_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            contact_frame,
            text="📞 Informações de Contato",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 15))

        # Contato
        self.create_field(contact_frame, "Pessoa de Contato", "contato")

        # Email
        self.create_field(contact_frame, "Email", "email")

        # Telefone
        self.create_field(contact_frame, "Telefone", "telefone")

        # Endereço
        self.create_field(contact_frame, "Endereço", "endereco", multiline=True)

        # Configurações de importação
        import_frame = ctk.CTkFrame(parent)
        import_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            import_frame,
            text="⚙️ Configurações de Importação",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 15))

        # Linha do cabeçalho padrão
        self.create_field(import_frame, "Linha do Cabeçalho Padrão", "linha_cabecalho", field_type="int",
                          default_value=1)

    def create_field(self, parent, label_text: str, field_name: str,
                     required: bool = False, multiline: bool = False,
                     field_type: str = "str", default_value=None):
        """Cria um campo do formulário"""
        # Frame do campo
        field_frame = ctk.CTkFrame(parent, fg_color="transparent")
        field_frame.pack(fill="x", padx=20, pady=5)

        # Label
        label = ctk.CTkLabel(
            field_frame,
            text=label_text,
            font=ctk.CTkFont(size=12, weight="bold" if required else "normal"),
            width=150
        )
        label.pack(side="left", padx=(0, 10), anchor="nw")

        # Campo de entrada
        if field_type == "int":
            var = tk.IntVar(value=default_value if default_value is not None else 0)
            entry = ctk.CTkEntry(
                field_frame,
                textvariable=var,
                height=30
            )
        elif multiline:
            var = tk.StringVar()
            entry = ctk.CTkTextbox(
                field_frame,
                height=80
            )
        else:
            var = tk.StringVar()
            entry = ctk.CTkEntry(
                field_frame,
                textvariable=var,
                height=30
            )

        if not multiline:
            entry.pack(side="left", fill="x", expand=True)
        else:
            entry.pack(fill="x", expand=True, pady=(0, 10))

        # Armazenar referências
        self.form_vars[field_name] = {
            'var': var if not multiline else None,
            'widget': entry,
            'required': required,
            'type': field_type,
            'multiline': multiline
        }

    def create_buttons(self, parent):
        """Cria botões do formulário"""
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

        # Salvar
        save_text = "💾 Atualizar" if self.is_editing else "💾 Salvar"
        ctk.CTkButton(
            buttons_frame,
            text=save_text,
            command=self.save,
            width=120,
            height=35
        ).pack(side="right")

    def populate_form(self):
        """Preenche formulário com dados do fornecedor"""
        if not self.fornecedor:
            return

        try:
            # Preencher campos
            field_mapping = {
                'nome': self.fornecedor.nome,
                'codigo': self.fornecedor.codigo,
                'cnpj': self.fornecedor.cnpj,
                'contato': self.fornecedor.contato,
                'email': self.fornecedor.email,
                'telefone': self.fornecedor.telefone,
                'endereco': self.fornecedor.endereco,
                'linha_cabecalho': self.fornecedor.linha_cabecalho
            }

            for field_name, value in field_mapping.items():
                if field_name in self.form_vars and value:
                    field_info = self.form_vars[field_name]

                    if field_info['multiline']:
                        field_info['widget'].delete("1.0", "end")
                        field_info['widget'].insert("1.0", str(value))
                    else:
                        field_info['var'].set(value)

        except Exception as e:
            logger.error(f"Erro ao preencher formulário: {e}")

    def validate_form(self) -> bool:
        """Valida dados do formulário"""
        try:
            # Verificar campos obrigatórios
            for field_name, field_info in self.form_vars.items():
                if field_info['required']:
                    if field_info['multiline']:
                        value = field_info['widget'].get("1.0", "end").strip()
                    else:
                        value = field_info['var'].get()

                    if not value or (isinstance(value, str) and not value.strip()):
                        messagebox.showerror("Erro", f"O campo '{field_name}' é obrigatório")
                        return False

            # Validar email se preenchido
            email_field = self.form_vars.get('email')
            if email_field and not email_field['multiline']:
                email = email_field['var'].get().strip()
                if email and '@' not in email:
                    messagebox.showerror("Erro", "Email inválido")
                    return False

            return True

        except Exception as e:
            logger.error(f"Erro na validação: {e}")
            messagebox.showerror("Erro", f"Erro na validação: {e}")
            return False

    def get_form_data(self) -> dict:
        """Obtém dados do formulário"""
        try:
            data = {}

            for field_name, field_info in self.form_vars.items():
                if field_info['multiline']:
                    value = field_info['widget'].get("1.0", "end").strip()
                else:
                    value = field_info['var'].get()

                # Converter tipo se necessário
                if field_info['type'] == 'int':
                    try:
                        value = int(value) if value else 0
                    except:
                        value = 0
                elif field_info['type'] == 'str':
                    value = str(value).strip() if value else ""

                data[field_name] = value

            return data

        except Exception as e:
            logger.error(f"Erro ao obter dados do formulário: {e}")
            raise

    def save(self):
        """Salva fornecedor"""
        try:
            # Validar formulário
            if not self.validate_form():
                return

            # Obter dados
            data = self.get_form_data()

            if self.is_editing:
                # Atualizar fornecedor existente
                self.fornecedor.nome = data['nome']
                self.fornecedor.codigo = data['codigo']
                self.fornecedor.cnpj = data['cnpj']
                self.fornecedor.contato = data['contato']
                self.fornecedor.email = data['email']
                self.fornecedor.telefone = data['telefone']
                self.fornecedor.endereco = data['endereco']
                self.fornecedor.linha_cabecalho = data['linha_cabecalho']

                success = self.db.update_fornecedor(self.fornecedor)

                if success:
                    messagebox.showinfo("Sucesso", "Fornecedor atualizado com sucesso!")
                    self.result = "success"
                    self.dialog.destroy()
                else:
                    messagebox.showerror("Erro", "Falha ao atualizar fornecedor")

            else:
                # Criar novo fornecedor
                fornecedor = FornecedorCustos(
                    nome=data['nome'],
                    codigo=data['codigo'],
                    cnpj=data['cnpj'],
                    contato=data['contato'],
                    email=data['email'],
                    telefone=data['telefone'],
                    endereco=data['endereco'],
                    linha_cabecalho=data['linha_cabecalho'],
                    estrutura_planilha="{}",
                    colunas_mapeamento="{}"
                )

                fornecedor_id = self.db.add_fornecedor(fornecedor)

                if fornecedor_id:
                    messagebox.showinfo("Sucesso", "Fornecedor cadastrado com sucesso!")
                    self.result = "success"
                    self.dialog.destroy()
                else:
                    messagebox.showerror("Erro", "Falha ao cadastrar fornecedor")

        except Exception as e:
            logger.error(f"Erro ao salvar fornecedor: {e}")
            messagebox.showerror("Erro", f"Erro ao salvar fornecedor:\n{e}")

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()