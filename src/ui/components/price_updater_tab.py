import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import asyncio
from typing import Optional, Callable, Any

from ..utils.logger import get_logger

logger = get_logger("price_updater_tab")


class PriceUpdaterTabFrame(ctk.CTkFrame):
    """
    Aba "Atualizador de Preços".
    Espera receber um objeto/serviço 'updater' com um método entrypoint (ver start_update).
    """

    def __init__(self, parent, updater: Any, config: Any):
        super().__init__(parent)
        self.updater = updater
        self.config = config
        self.running = False

        self.file_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Pronto para atualizar preços")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="💸 Atualizador Automático de Preços", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(anchor="w", padx=20, pady=(20, 8))

        subtitle = ctk.CTkLabel(
            self,
            text="Selecione o arquivo de entrada e rode a atualização. O processamento ocorre em segundo plano.",
            text_color=("gray60", "gray40"),
            wraplength=900,
            justify="left",
        )
        subtitle.pack(anchor="w", padx=20, pady=(0, 16))

        # Seleção de arquivo
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkLabel(box, text="Arquivo de entrada *", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=15, pady=(12, 6))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 12))

        self.file_entry = ctk.CTkEntry(row, textvariable=self.file_var, placeholder_text="Selecione o arquivo...")
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(row, text="📂 Procurar", width=140, command=self._select_file).pack(side="right")

        # Ações
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 10))

        self.btn_run = ctk.CTkButton(
            actions,
            text="▶️ Atualizar Preços",
            height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.start_update,
        )
        self.btn_run.pack(side="left")

        self.btn_cancel = ctk.CTkButton(
            actions,
            text="⏹️ Cancelar",
            height=44,
            fg_color=("gray30", "gray25"),
            command=self._cancel,
            state="disabled"
        )
        self.btn_cancel.pack(side="left", padx=(10, 0))

        # Status / Progresso
        status_box = ctk.CTkFrame(self)
        status_box.pack(fill="x", padx=20, pady=(10, 20))

        self.status_label = ctk.CTkLabel(status_box, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill="x", padx=15, pady=(12, 6))

        self.progress = ctk.CTkProgressBar(status_box, variable=self.progress_var)
        self.progress.pack(fill="x", padx=15, pady=(0, 12))

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Selecionar arquivo",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.file_var.set(path)

    def _cancel(self):
        # Se seu updater suportar cancelamento, conecte aqui.
        # Ex.: self.updater.cancel() ou setar flag
        self.status_var.set("Cancelamento solicitado...")
        logger.warning("Cancelamento solicitado (implementar no updater se necessário).")

    def start_update(self):
        if self.running:
            messagebox.showwarning("Aviso", "Atualização já está em andamento.")
            return

        if not self.file_var.get():
            messagebox.showerror("Erro", "Selecione um arquivo de entrada.")
            return

        file_path = Path(self.file_var.get())
        if not file_path.exists():
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{file_path}")
            return

        self.running = True
        self.btn_run.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.status_var.set("⏳ Iniciando...")
        self.progress_var.set(0.0)

        thread = threading.Thread(target=self._run_update_thread, args=(file_path,), daemon=True)
        thread.start()

    def _run_update_thread(self, file_path: Path):
        try:
            def status_cb(msg: str):
                self.after(0, lambda: self.status_var.set(msg))

            def progress_cb(v: float):
                vv = max(0.0, min(1.0, float(v)))
                self.after(0, lambda: self.progress_var.set(vv))

            # ---- CHAME AQUI SEU ENTRYPOINT ----
            # Você tem 2 formatos comuns:
            #
            # (A) SÍNCRONO:
            # result = self.updater.update_prices(input_file=file_path, status_callback=status_cb, progress_callback=progress_cb)
            #
            # (B) ASSÍNCRONO (async def):
            # result = asyncio.run(self.updater.update_prices(input_file=file_path, status_callback=status_cb, progress_callback=progress_cb))
            #
            # Ajuste o nome do método abaixo para o seu projeto:
            entry = getattr(self.updater, "update_prices", None) or getattr(self.updater, "run", None)
            if entry is None:
                raise RuntimeError("Updater não possui método 'update_prices' nem 'run'.")

            if asyncio.iscoroutinefunction(entry):
                result = asyncio.run(entry(input_file=file_path, status_callback=status_cb, progress_callback=progress_cb))
            else:
                result = entry(input_file=file_path, status_callback=status_cb, progress_callback=progress_cb)

            logger.success("Atualização de preços finalizada.")
            self.after(0, lambda: messagebox.showinfo("Sucesso", "✅ Atualização de preços concluída!"))

        except Exception as e:
            logger.error(f"Erro no atualizador de preços: {e}")
            self.after(0, lambda: messagebox.showerror("Erro", f"Erro ao atualizar preços:\n{e}"))

        finally:
            self.running = False
            self.after(0, self._ui_end)

    def _ui_end(self):
        self.btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.status_var.set("Pronto para atualizar preços")
        self.progress_var.set(0.0)