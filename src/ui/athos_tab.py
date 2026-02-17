import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading

from ..utils.logger import get_logger
from ..services.athos_runner import AthosRunner

logger = get_logger("athos_tab")


class AthosTab(ctk.CTkFrame):
    def __init__(self, parent, output_dir: Path):
        super().__init__(parent)

        self.output_dir = Path(output_dir)

        self.sql_var = tk.StringVar()
        self.whitelist_var = tk.StringVar()
        self.template_var = tk.StringVar()

        self.status_var = tk.StringVar(value="Pronto para gerar planilhas do Robô Athos")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(
            self,
            text="🤖 Robô Athos",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w"
        )
        title.pack(fill="x", padx=10, pady=(10, 5))

        subtitle = ctk.CTkLabel(
            self,
            text="Gera 5 planilhas (aba PRODUTOS) + relatório consolidado a partir do export do SQL",
            text_color=("gray60", "gray40"),
            anchor="w"
        )
        subtitle.pack(fill="x", padx=10, pady=(0, 15))

        self._file_picker("📄 Export do SQL (Excel)", self.sql_var, self._pick_sql)
        self._file_picker("✅ Whitelist (PRODUTOS.xls/.xlsx)", self.whitelist_var, self._pick_whitelist)
        self._file_picker("📌 Template Athos (xlsx/xlsm)", self.template_var, self._pick_template)

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=10, pady=10)

        self.btn_run = ctk.CTkButton(
            actions,
            text="⚙️ Gerar planilhas + relatório",
            height=44,
            command=self._start_run
        )
        self.btn_run.pack(side="left")

        self.btn_open = ctk.CTkButton(
            actions,
            text="📁 Abrir pasta de saída",
            height=44,
            command=self._open_output
        )
        self.btn_open.pack(side="left", padx=(10, 0))

        status = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        status.pack(fill="x", padx=10, pady=(10, 5))

        self.bar = ctk.CTkProgressBar(self, variable=self.progress_var)
        self.bar.pack(fill="x", padx=10, pady=(0, 10))

    def _file_picker(self, label, var, cmd):
        wrap = ctk.CTkFrame(self)
        wrap.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(wrap, text=label, anchor="w").pack(fill="x", padx=10, pady=(10, 5))

        row = ctk.CTkFrame(wrap)
        row.pack(fill="x", padx=10, pady=(0, 10))

        entry = ctk.CTkEntry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn = ctk.CTkButton(row, text="📂 Procurar", width=120, command=cmd)
        btn.pack(side="right")

    def _pick_sql(self):
        p = filedialog.askopenfilename(
            title="Selecionar export do SQL",
            filetypes=[("Excel", "*.xlsx *.xls *.xlsm"), ("All files", "*.*")]
        )
        if p:
            self.sql_var.set(p)

    def _pick_whitelist(self):
        p = filedialog.askopenfilename(
            title="Selecionar whitelist",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if p:
            self.whitelist_var.set(p)

    def _pick_template(self):
        p = filedialog.askopenfilename(
            title="Selecionar template Athos",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")]
        )
        if p:
            self.template_var.set(p)

    def _start_run(self):
        sql_p = Path(self.sql_var.get().strip())
        wl_p = Path(self.whitelist_var.get().strip())
        tpl_p = Path(self.template_var.get().strip())

        if not sql_p.exists():
            messagebox.showerror("Erro", "Selecione um export do SQL válido.")
            return
        if not wl_p.exists():
            messagebox.showerror("Erro", "Selecione uma whitelist válida.")
            return
        if not tpl_p.exists():
            messagebox.showerror("Erro", "Selecione um template Athos válido.")
            return

        self.btn_run.configure(state="disabled", text="🔄 Gerando...")
        self.progress_var.set(0.0)
        self.status_var.set("Iniciando...")

        def worker():
            try:
                runner = AthosRunner(output_dir=self.output_dir)

                def progress(pct: float, msg: str = ""):
                    self.after(0, lambda: self.progress_var.set(float(pct)))
                    if msg:
                        self.after(0, lambda: self.status_var.set(msg))

                result = runner.run(
                    sql_export_path=sql_p,
                    whitelist_path=wl_p,
                    template_path=tpl_p,
                    progress_callback=progress
                )

                self.after(0, lambda: self.status_var.set(
                    f"✅ Concluído! Arquivos gerados: {len(result.generated_files)} | Relatório: {result.report_path}"
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "Robô Athos",
                    "✅ Planilhas base + relatório gerados com sucesso!\n\n"
                    f"Pasta: {self.output_dir}"
                ))

            except Exception as e:
                logger.error(f"Erro no Robô Athos: {e}")
                self.after(0, lambda: messagebox.showerror("Erro", f"❌ Falha ao gerar:\n{e}"))
                self.after(0, lambda: self.status_var.set(f"❌ Erro: {e}"))
            finally:
                self.after(0, lambda: self.btn_run.configure(state="normal", text="⚙️ Gerar planilhas + relatório"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_output(self):
        import os, platform, subprocess
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)

        try:
            if platform.system() == "Windows":
                os.startfile(out)
            elif platform.system() == "Darwin":
                subprocess.run(["open", out])
            else:
                subprocess.run(["xdg-open", out])
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")
