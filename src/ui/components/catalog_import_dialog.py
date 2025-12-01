"""Diálogo para importação do catálogo de produtos"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import threading
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CatalogImportDialog:
    """Diálogo para importação do catálogo"""

    def __init__(self, parent, db):
        self.parent = parent
        self.db = db
        self.result = None

        # Criar janela
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("📥 Importar Catálogo de Produtos")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centralizar
        self.center_window()

        # Variáveis
        self.file_path = None
        self.preview_data = None

        # Criar interface
        self.create_widgets()

    def center_window(self):
        """Centraliza a janela"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 800) // 2
        y = (self.dialog.winfo_screenheight() - 600) // 2
        self.dialog.geometry(f"800x600+{x}+{y}")

    def create_widgets(self):
        """Cria os widgets da interface"""
        # Frame principal
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="📥 Importar Catálogo de Produtos",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(20, 30))

        # Seção de seleção de arquivo
        self.create_file_section(main_frame)

        # Seção de prévia
        self.create_preview_section(main_frame)

        # Seção de opções
        self.create_options_section(main_frame)

        # Botões
        self.create_buttons_section(main_frame)

    def create_file_section(self, parent):
        """Cria seção de seleção de arquivo"""
        file_frame = ctk.CTkFrame(parent)
        file_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            file_frame,
            text="📁 Selecionar Arquivo:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Frame para arquivo
        file_input_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        file_input_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.file_var = tk.StringVar()
        self.file_entry = ctk.CTkEntry(
            file_input_frame,
            textvariable=self.file_var,
            placeholder_text="Selecione a planilha do catálogo...",
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

    def create_preview_section(self, parent):
        """Cria seção de prévia"""
        self.preview_frame = ctk.CTkFrame(parent)
        self.preview_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkLabel(
            self.preview_frame,
            text="👁️ Prévia da Importação:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Área de texto para prévia
        self.preview_text = ctk.CTkTextbox(
            self.preview_frame,
            height=200,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.preview_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Texto inicial
        self.preview_text.insert("1.0", "Selecione um arquivo para ver a prévia da importação...")
        self.preview_text.configure(state="disabled")

    def create_options_section(self, parent):
        """Cria seção de opções"""
        options_frame = ctk.CTkFrame(parent)
        options_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            options_frame,
            text="⚙️ Opções de Importação:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Opções
        options_inner = ctk.CTkFrame(options_frame, fg_color="transparent")
        options_inner.pack(fill="x", padx=20, pady=(0, 20))

        self.update_existing_var = tk.BooleanVar(value=True)
        self.update_checkbox = ctk.CTkCheckBox(
            options_inner,
            text="Atualizar produtos existentes (baseado no COD AUXILIAR/COD BARRA)",
            variable=self.update_existing_var
        )
        self.update_checkbox.pack(anchor="w", pady=(0, 10))

        self.clear_before_var = tk.BooleanVar(value=False)
        self.clear_checkbox = ctk.CTkCheckBox(
            options_inner,
            text="Limpar catálogo antes de importar (⚠️ Remove todos os dados)",
            variable=self.clear_before_var
        )
        self.clear_checkbox.pack(anchor="w")

    def create_buttons_section(self, parent):
        """Cria seção de botões"""
        buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            buttons_frame,
            text="❌ Cancelar",
            command=self.cancel,
            width=120,
            height=35
        ).pack(side="right", padx=(10, 0))

        self.import_button = ctk.CTkButton(
            buttons_frame,
            text="📥 Importar",
            command=self.start_import,
            width=120,
            height=35,
            state="disabled"
        )
        self.import_button.pack(side="right")

        self.validate_button = ctk.CTkButton(
            buttons_frame,
            text="🔍 Validar Planilha",
            command=self.validate_file,
            width=140,
            height=35,
            state="disabled"
        )
        self.validate_button.pack(side="left")

    def select_file(self):
        """Seleciona arquivo da planilha"""
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha do Catálogo",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            self.file_path = Path(file_path)
            self.file_var.set(str(self.file_path))

            # Habilitar botões
            self.import_button.configure(state="normal")
            self.validate_button.configure(state="normal")

            # Gerar prévia automaticamente
            self.generate_preview()

    def generate_preview(self):
        """Gera prévia da importação"""
        if not self.file_path:
            return

        try:
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", "🔄 Gerando prévia...")
            self.preview_text.configure(state="disabled")

            # Gerar prévia em thread separada
            def generate():
                try:
                    from ...services.catalog_importer import CatalogImporter
                    importer = CatalogImporter(self.db)
                    preview = importer.get_import_preview(self.file_path)

                    # Atualizar interface
                    self.dialog.after(0, lambda: self.show_preview(preview))

                except Exception as e:
                    error_msg = f"Erro ao gerar prévia: {str(e)}"
                    logger.error(error_msg)
                    self.dialog.after(0, lambda: self.show_preview_error(error_msg))

            thread = threading.Thread(target=generate, daemon=True)
            thread.start()

        except Exception as e:
            error_msg = f"Erro ao iniciar prévia: {str(e)}"
            logger.error(error_msg)
            self.show_preview_error(error_msg)

    def show_preview(self, preview: dict):
        """Mostra prévia na interface"""
        try:
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")

            if "error" in preview:
                self.preview_text.insert("1.0", f"❌ Erro: {preview['error']}")
                self.import_button.configure(state="disabled")
                self.preview_text.configure(state="disabled")
                return

            # Montar texto da prévia
            preview_text = f"""📊 PRÉVIA DA IMPORTAÇÃO

📁 Arquivo: {self.file_path.name}
📊 Total de linhas: {preview['total_rows']}
📦 Produtos estimados: {preview['estimated_products']}

��️ COLUNAS ENCONTRADAS ({len(preview['columns_found'])}):
{chr(10).join(f"  • {col}" for col in preview['columns_found'])}

✅ COLUNAS MAPEADAS ({len(preview['columns_mapped'])}):
{chr(10).join(f"  • {mapping}" for mapping in preview['columns_mapped'])}
"""

            if preview['columns_missing']:
                preview_text += f"""

⚠️ COLUNAS NÃO ENCONTRADAS ({len(preview['columns_missing'])}):
{chr(10).join(f"  • {col}" for col in preview['columns_missing'])}
"""

            if preview['sample_data']:
                preview_text += f"""

📋 AMOSTRA DOS PRIMEIROS PRODUTOS:
"""
                for sample in preview['sample_data']:
                    preview_text += f"""  Linha {sample['linha']}:
    Marca: {sample['marca']}
    Cód. Auxiliar: {sample['cod_auxiliar']}
    Cód. Barra: {sample['cod_barra']}
    Categoria: {sample['categoria']}
    Preço: {sample['preco']}
    Promoção: {sample['promocao']}

"""

            self.preview_text.insert("1.0", preview_text)
            self.preview_text.configure(state="disabled")

            # Habilitar importação se tudo OK
            if preview['estimated_products'] > 0:
                self.import_button.configure(state="normal")
            else:
                self.import_button.configure(state="disabled")

        except Exception as e:
            self.show_preview_error(f"Erro ao exibir prévia: {str(e)}")

    def show_preview_error(self, error_msg: str):
        """Mostra erro na prévia"""
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", f"❌ {error_msg}")
        self.preview_text.configure(state="disabled")
        self.import_button.configure(state="disabled")

    def validate_file(self):
        """Valida estrutura do arquivo"""
        if not self.file_path:
            messagebox.showwarning("Aviso", "Selecione um arquivo primeiro")
            return

        try:
            from ...services.catalog_importer import CatalogImporter
            importer = CatalogImporter(self.db)
            validation = importer.validate_excel_structure(self.file_path)

            if validation["valid"]:
                message = (
                    f"✅ Planilha válida!\n\n"
                    f"📋 Total de linhas: {validation['total_rows']}\n"
                    f"📊 Total de colunas: {validation['total_columns']}\n"
                    f"✅ Colunas obrigatórias encontradas: {validation['required_columns_found']}"
                )

                if validation["warnings"]:
                    message += f"\n\n⚠️ Avisos:\n" + "\n".join(f"• {w}" for w in validation["warnings"])

                messagebox.showinfo("Validação", message)
            else:
                error_msg = validation.get("error", "Planilha inválida")
                message = f"❌ {error_msg}"

                if validation.get("missing_columns"):
                    message += f"\n\nColunas faltando:\n" + "\n".join(f"• {col}" for col in validation["missing_columns"])

                messagebox.showerror("Validação", message)

        except Exception as e:
            messagebox.showerror("Erro", f"Erro na validação:\n{str(e)}")

    def start_import(self):
        """Inicia importação"""
        if not self.file_path:
            messagebox.showwarning("Aviso", "Selecione um arquivo primeiro")
            return

        # Confirmar importação
        clear_text = "SIM - Limpar catálogo e importar" if self.clear_before_var.get() else "NÃO - Manter dados existentes"
        update_text = "SIM - Atualizar existentes" if self.update_existing_var.get() else "NÃO - Ignorar existentes"

        response = messagebox.askyesno(
            "Confirmar Importação",
            f"Confirma a importação do catálogo?\n\n"
            f"📁 Arquivo: {self.file_path.name}\n"
            f"🗑️ Limpar dados existentes: {clear_text}\n"
            f"🔄 Atualizar produtos existentes: {update_text}\n\n"
            f"Esta operação pode demorar alguns minutos."
        )

        if not response:
            return

        # Executar importação
        self.execute_import()

    def execute_import(self):
        """Executa a importação"""
        # Criar diálogo de progresso
        self.create_progress_dialog()

        def run_import():
            try:
                from ...services.catalog_importer import CatalogImporter
                importer = CatalogImporter(self.db)

                if self.clear_before_var.get():
                    result = importer.clear_and_reimport(
                        self.file_path,
                        progress_callback=self.update_progress,
                        status_callback=self.update_status
                    )
                else:
                    result = importer.import_from_excel(
                        self.file_path,
                        update_existing=self.update_existing_var.get(),
                        progress_callback=self.update_progress,
                        status_callback=self.update_status
                    )

                # Finalizar na thread principal
                self.dialog.after(0, lambda: self.import_completed(result))

            except ImportError as e:
                error_msg = f"Erro ao importar módulo: {str(e)}"
                logger.error(error_msg)
                self.dialog.after(0, lambda: self.import_error(error_msg))
            except Exception as e:
                error_msg = f"Erro na importação: {str(e)}"
                logger.error(error_msg)
                self.dialog.after(0, lambda: self.import_error(error_msg))

        thread = threading.Thread(target=run_import, daemon=True)
        thread.start()

    def create_progress_dialog(self):
        """Cria diálogo de progresso"""
        self.progress_dialog = ctk.CTkToplevel(self.dialog)
        self.progress_dialog.title("📥 Importando Catálogo")
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
        self.status_var = tk.StringVar(value="Iniciando importação...")
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

    def import_completed(self, result):
        """Callback quando importação é concluída"""
        try:
            # Fechar diálogo de progresso
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.destroy()

            # Mostrar resultado
            if result.success:
                message = (
                    f"✅ Importação concluída com sucesso!\n\n"
                    f"📦 Total processado: {result.total_produtos}\n"
                    f"➕ Produtos novos: {result.produtos_novos}\n"
                    f"🔄 Produtos atualizados: {result.produtos_atualizados}\n"
                    f"⏭️ Produtos ignorados: {result.produtos_ignorados}\n"
                    f"⏱️ Tempo: {result.processing_time:.2f}s"
                )

                if result.warnings:
                    message += f"\n\n⚠️ Avisos ({len(result.warnings)}):\n" + "\n".join(f"• {w}" for w in result.warnings[:3])
                    if len(result.warnings) > 3:
                        message += f"\n... e mais {len(result.warnings) - 3} avisos"

                messagebox.showinfo("Sucesso", message)
                self.result = "success"
                self.dialog.destroy()

            else:
                error_msg = (
                    f"❌ Importação falhou!\n\n"
                    f"⏱️ Tempo: {result.processing_time:.2f}s\n\n"
                    f"Erros ({len(result.errors)}):\n"
                )
                error_msg += "\n".join(f"• {e}" for e in result.errors[:5])

                if len(result.errors) > 5:
                    error_msg += f"\n... e mais {len(result.errors) - 5} erros"

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

    def cancel(self):
        """Cancela o diálogo"""
        self.dialog.destroy()