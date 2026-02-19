"""
Tela: Robô Athos (ABA)
- Importa arquivo(s) (SQL export / whitelist / template)
- Executa geração das 5 planilhas + relatório (via service)
- Mantém UI no padrão do projeto (CustomTkinter) e roda em thread
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
from pathlib import Path
from datetime import datetime
import traceback

from ..core.config import load_config
from ..utils.logger import get_logger

logger = get_logger("athos_ui")

try:
    from ..services.athos_runner import AthosRunner  # type: ignore
except Exception:
    AthosRunner = None  # type: ignore


class AthosTabFrame(ctk.CTkFrame):
    """UI do Robô Athos para ser embutida em uma aba."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.config_data = load_config()

        self.processing = False
        self.cancel_requested = False

        self.sql_export_var = tk.StringVar(value="")
        self.whitelist_var = tk.StringVar(value="")
        self.template_var = tk.StringVar(value="")
        self.output_dir_var = tk.StringVar(value=str(self.config_data.output_dir))

        self.status_var = tk.StringVar(value="Pronto")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.send_email_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _safe_after(self, ms: int, fn):
        try:
            if self.winfo_exists():
                self.after(ms, fn)
        except Exception:
            pass

    def _build_ui(self):
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True)

        self._section_files(body)
        self._section_actions(body)
        self._section_logs(body)

        footer = ctk.CTkFrame(self, height=70)
        footer.pack(fill="x", pady=(10, 0))
        footer.pack_propagate(False)

        status_row = ctk.CTkFrame(footer, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(10, 0))

        ctk.CTkLabel(status_row, text="Status:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkLabel(status_row, textvariable=self.status_var, font=ctk.CTkFont(size=13)).pack(
            side="left", fill="x", expand=True
        )

        self.progress_bar = ctk.CTkProgressBar(footer, variable=self.progress_var, height=18)
        self.progress_bar.pack(fill="x", padx=16, pady=(8, 14))
        self.progress_bar.set(0.0)

    def _section_files(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            frame, text="📁 Arquivos", font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(16, 10))

        self._file_row(
            frame,
            label="Arquivo com resultado do SQL (export Excel) *",
            var=self.sql_export_var,
            button_text="📂 Selecionar",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )

        self._file_row(
            frame,
            label="Whitelist (PRODUTOS.xls / lista de imediatos) *",
            var=self.whitelist_var,
            button_text="📂 Selecionar",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )

        self._file_row(
            frame,
            label="Template Athos (planilha modelo) *",
            var=self.template_var,
            button_text="📂 Selecionar",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(6, 18))

        ctk.CTkLabel(row, text="Pasta de saída:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", pady=(0, 6)
        )

        box = ctk.CTkFrame(row)
        box.pack(fill="x")

        entry = ctk.CTkEntry(box, textvariable=self.output_dir_var, placeholder_text="outputs/ ...")
        entry.pack(side="left", fill="x", expand=True, padx=(12, 10), pady=12)

        ctk.CTkButton(
            box,
            text="📁 Pasta",
            width=120,
            command=self._select_output_dir,
        ).pack(side="right", padx=(0, 12), pady=12)

    def _section_actions(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            frame, text="⚙️ Ações", font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(16, 10))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkCheckBox(
            btn_row,
            text="📧 Enviar automaticamente para rpa.athus@apoiocorp.com.br",
            variable=self.send_email_var,
        ).pack(side="top", anchor="w", pady=(0, 10))

        self.run_btn = ctk.CTkButton(
            btn_row,
            text="🔁 Atualizar Imediatos (gerar 5 planilhas + relatório)",
            height=52,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_processing,
        )
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            btn_row,
            text="🛑 Cancelar",
            width=140,
            height=52,
            command=self._request_cancel,
            state="disabled",
        )
        self.cancel_btn.pack(side="right")

    def _section_logs(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame, text="🧾 Log / Resultado", font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(16, 10))

        self.log_text = ctk.CTkTextbox(frame, height=220)
        self.log_text.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self._log("Robô Athos pronto. Selecione os arquivos e clique em “Atualizar Imediatos”.")

    def _file_row(self, parent, label: str, var: tk.StringVar, button_text: str, filetypes):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="x", padx=18, pady=8)

        ctk.CTkLabel(container, text=label, font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", pady=(0, 6)
        )

        box = ctk.CTkFrame(container)
        box.pack(fill="x")

        entry = ctk.CTkEntry(box, textvariable=var, placeholder_text="Selecione o arquivo...")
        entry.pack(side="left", fill="x", expand=True, padx=(12, 10), pady=12)

        ctk.CTkButton(
            box,
            text=button_text,
            width=140,
            command=lambda: self._select_file(var, filetypes),
        ).pack(side="right", padx=(0, 12), pady=12)

    def _select_file(self, var: tk.StringVar, filetypes):
        path = filedialog.askopenfilename(title="Selecionar arquivo", filetypes=filetypes)
        if path:
            var.set(path)

    def _select_output_dir(self):
        path = filedialog.askdirectory(title="Selecionar pasta de saída")
        if path:
            self.output_dir_var.set(path)

    def _start_processing(self):
        if self.processing:
            messagebox.showwarning("Aviso", "Processamento já está em andamento.")
            return

        sql_path = Path(self.sql_export_var.get().strip()) if self.sql_export_var.get().strip() else None
        wl_path = Path(self.whitelist_var.get().strip()) if self.whitelist_var.get().strip() else None
        tpl_path = Path(self.template_var.get().strip()) if self.template_var.get().strip() else None
        out_dir = Path(self.output_dir_var.get().strip()) if self.output_dir_var.get().strip() else None

        missing = []
        if not sql_path or not sql_path.exists():
            missing.append("• Arquivo resultado SQL (Excel)")
        if not wl_path or not wl_path.exists():
            missing.append("• Whitelist (lista de imediatos)")
        if not tpl_path or not tpl_path.exists():
            missing.append("• Template Athos (modelo)")
        if not out_dir:
            missing.append("• Pasta de saída")

        if missing:
            messagebox.showerror("Campos obrigatórios", "Faltam itens:\n" + "\n".join(missing))
            return

        self.processing = True
        self.cancel_requested = False
        self.run_btn.configure(state="disabled", text="⏳ Processando...")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0.0)
        self.status_var.set("Iniciando...")

        thread = threading.Thread(
            target=self._run_processing_thread,
            args=(sql_path, wl_path, tpl_path, out_dir, bool(self.send_email_var.get())),
            daemon=True,
        )
        thread.start()

    def _request_cancel(self):
        if not self.processing:
            return
        self.cancel_requested = True
        self.status_var.set("Cancelamento solicitado...")

    def _run_processing_thread(self, sql_path: Path, wl_path: Path, tpl_path: Path, out_dir: Path, send_email: bool):
        try:
            started = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self._ui_log(f"🚀 Início: {started}")
            self._ui_log(f"SQL export: {sql_path}")
            self._ui_log(f"Whitelist: {wl_path}")
            self._ui_log(f"Template: {tpl_path}")
            self._ui_log(f"Saída: {out_dir}")
            self._ui_status("Validando serviço...")

            if AthosRunner is None:
                self._ui_log("❌ Service AthosRunner não encontrado/importável.")
                self._ui_fail("Service não encontrado (athos_runner.py).")
                return

            out_dir.mkdir(parents=True, exist_ok=True)

            runner = AthosRunner(output_dir=out_dir, logger=logger)

            def progress(p: float, msg: str = ""):
                if self.cancel_requested:
                    raise RuntimeError("CANCELLED_BY_USER")
                p = max(0.0, min(1.0, float(p)))
                self._ui_progress(p)
                if msg:
                    self._ui_status(msg)

            self._ui_status("Executando regras...")
            result = runner.run(
                sql_export_path=sql_path,
                whitelist_path=wl_path,
                template_path=tpl_path,
                progress_callback=progress,
                send_email=send_email,
            )

            self._ui_progress(1.0)
            self._ui_status("Concluído ✅")

            self._ui_log("")
            self._ui_log("✅ Arquivos gerados:")
            for p in getattr(result, "generated_files", []) or []:
                self._ui_log(f" - {p}")

            report_path = getattr(result, "report_path", None)
            if report_path:
                self._ui_log(f"🧾 Relatório: {report_path}")

            finished = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self._ui_log(f"🏁 Fim: {finished}")

            self._ui_done("Processamento concluído com sucesso!")

        except RuntimeError as e:
            if str(e) == "CANCELLED_BY_USER":
                self._ui_log("🛑 Cancelado pelo usuário.")
                self._ui_fail("Cancelado.")
            else:
                self._ui_log(f"❌ ERRO (RuntimeError)\n{e}")
                self._ui_log("\n📌 Stacktrace:\n" + traceback.format_exc())
                self._ui_fail("Erro no processamento.")
        except Exception as e:
            self._ui_log(f"❌ ERRO ({type(e).__name__})\n{e}")
            self._ui_log("\n📌 Stacktrace:\n" + traceback.format_exc())
            logger.error(f"Erro no Robô Athos: {e}")
            self._ui_fail("Erro no processamento.")
        finally:
            self._ui_reset_buttons()

    def _ui_reset_buttons(self):
        def _apply():
            self.processing = False
            self.cancel_requested = False
            try:
                self.run_btn.configure(state="normal", text="🔁 Atualizar Imediatos (gerar 5 planilhas + relatório)")
                self.cancel_btn.configure(state="disabled")
            except Exception:
                pass
        self._safe_after(0, _apply)

    def _ui_progress(self, value: float):
        self._safe_after(0, lambda: self.progress_bar.set(value))

    def _ui_status(self, msg: str):
        self._safe_after(0, lambda: self.status_var.set(msg))

    def _ui_log(self, msg: str):
        self._safe_after(0, lambda: self._log(msg))

    def _ui_fail(self, status: str):
        def _apply():
            self.status_var.set(status)
            self.progress_bar.set(0.0)
        self._safe_after(0, _apply)

    def _ui_done(self, toast: str):
        def _apply():
            try:
                if self.winfo_exists():
                    messagebox.showinfo("Robô Athos", toast)
            except Exception:
                pass
        self._safe_after(0, _apply)

    def _log(self, msg: str):
        try:
            if not self.winfo_exists():
                return
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
        except Exception:
            pass


class AthosWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("🤖 Robô Athos")
        self.geometry("900x720")
        self.minsize(820, 650)
        self.transient(master)
        self.lift()
        self.focus_force()

        frame = AthosTabFrame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
