import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import inspect

from ...utils.logger import get_logger

logger = get_logger("price_updater_tab")


class PriceUpdaterTabFrame(ctk.CTkFrame):
    def __init__(self, parent, updater, config=None):
        super().__init__(parent)
        self.updater = updater
        self.config = config
        self.running = False

        self.base_var = tk.StringVar(value="")
        self.products_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="Fábrica")
        self.rule90_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Pronto para atualizar preços")
        self.progress_var = tk.DoubleVar(value=0.0)

        # Se seu service tiver config interna (ConfigManager), tenta puxar base salva
        try:
            if hasattr(self.updater, "get_saved_base_file"):
                saved = self.updater.get_saved_base_file()
                if saved:
                    self.base_var.set(saved)
            elif hasattr(self.updater, "config") and hasattr(self.updater.config, "get_base_file_path"):
                saved = self.updater.config.get_base_file_path()
                if saved:
                    self.base_var.set(saved)
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="💸 Atualizador Automático de Preços", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=20, pady=(20, 8))

        # BASE
        box_base = ctk.CTkFrame(self)
        box_base.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(box_base, text="Planilha BASE (custos) *", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=15, pady=(12, 6))

        rowb = ctk.CTkFrame(box_base, fg_color="transparent")
        rowb.pack(fill="x", padx=15, pady=(0, 12))
        ctk.CTkEntry(rowb, textvariable=self.base_var, placeholder_text="Selecione a planilha base...").pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(rowb, text="📂 Procurar", width=140, command=self._pick_base).pack(side="right")

        # PRODUTOS
        box_prod = ctk.CTkFrame(self)
        box_prod.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(box_prod, text="Planilha de PRODUTOS (será atualizada) *", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=15, pady=(12, 6))

        rowp = ctk.CTkFrame(box_prod, fg_color="transparent")
        rowp.pack(fill="x", padx=15, pady=(0, 12))
        ctk.CTkEntry(rowp, textvariable=self.products_var, placeholder_text="Selecione a planilha de produtos...").pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(rowp, text="📂 Procurar", width=140, command=self._pick_products).pack(side="right")

        # OPÇÕES
        box_opt = ctk.CTkFrame(self)
        box_opt.pack(fill="x", padx=20, pady=(0, 12))
        ropt = ctk.CTkFrame(box_opt, fg_color="transparent")
        ropt.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(ropt, text="Modo:", width=60, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(ropt, values=["Fábrica", "Fornecedor"], variable=self.mode_var, width=170).pack(side="left", padx=(0, 18))
        ctk.CTkCheckBox(ropt, text="Aplicar regra do ,90", variable=self.rule90_var).pack(side="left")

        # AÇÕES
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 10))

        self.btn_run = ctk.CTkButton(actions, text="▶️ Atualizar Preços", height=44, font=ctk.CTkFont(size=16, weight="bold"), command=self.start_update)
        self.btn_run.pack(side="left")

        # STATUS/PROGRESSO
        status_box = ctk.CTkFrame(self)
        status_box.pack(fill="x", padx=20, pady=(10, 20))

        ctk.CTkLabel(status_box, textvariable=self.status_var, anchor="w").pack(fill="x", padx=15, pady=(12, 6))
        ctk.CTkProgressBar(status_box, variable=self.progress_var).pack(fill="x", padx=15, pady=(0, 12))

    def _pick_base(self):
        p = filedialog.askopenfilename(title="Selecionar planilha BASE", filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")])
        if p:
            self.base_var.set(p)

    def _pick_products(self):
        p = filedialog.askopenfilename(title="Selecionar planilha de PRODUTOS", filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")])
        if p:
            self.products_var.set(p)

    def start_update(self):
        if self.running:
            messagebox.showwarning("Aviso", "Atualização já está em andamento.")
            return

        base_path = Path(self.base_var.get().strip())
        products_path = Path(self.products_var.get().strip())

        if not base_path.exists():
            messagebox.showerror("Erro", "Selecione uma planilha BASE válida.")
            return

        if not products_path.exists():
            messagebox.showerror("Erro", "Selecione uma planilha de PRODUTOS válida.")
            return

        self.running = True
        self.btn_run.configure(state="disabled")
        self.status_var.set("⏳ Iniciando...")
        self.progress_var.set(0.0)

        t = threading.Thread(target=self._run_update_thread, args=(base_path, products_path), daemon=True)
        t.start()

    def _call_with_accepted_kwargs(self, fn, **kwargs):
        sig = inspect.signature(fn)
        accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return fn(**accepted)

    def _run_update_thread(self, base_path: Path, products_path: Path):
        try:
            def log_cb(msg: str):
                self.after(0, lambda m=msg: self.status_var.set(m))

            def progress_cb(v: float):
                vv = max(0.0, min(1.0, float(v)))
                self.after(0, lambda x=vv: self.progress_var.set(x))

            mode = self.mode_var.get()
            apply90 = bool(self.rule90_var.get())

            # ✅ chama o service com base+produtos+modo (sem input_file)
            # Compatível com dois estilos comuns do TXT:
            # - PriceUpdaterService.run(...)
            # - ExcelProcessorUnified.process_files(...)
            if hasattr(self.updater, "run"):
                run_fn = getattr(self.updater, "run")

                result = self._call_with_accepted_kwargs(
                    run_fn,
                    base_file=base_path,
                    products_file=products_path,
                    mode=mode,
                    apply_90_cents_rule=apply90,

                    # callbacks (manda variações e deixa o helper escolher)
                    log_callback=log_cb,
                    status_callback=log_cb,
                    message_callback=log_cb,

                    progress_callback=progress_cb,
                    on_progress=progress_cb,
                )

            elif hasattr(self.updater, "process_files"):
                fn = getattr(self.updater, "process_files")

                result = self._call_with_accepted_kwargs(
                    fn,
                    products_file=str(products_path),
                    base_file=str(base_path),

                    log_callback=log_cb,
                    status_callback=log_cb,
                    message_callback=log_cb,

                    progress_callback=progress_cb,
                    on_progress=progress_cb,
                )
            else:
                raise RuntimeError("Updater não possui 'run' nem 'process_files'.")

            logger.success("Atualização de preços finalizada.")
            self.after(0, lambda: messagebox.showinfo("Sucesso", "✅ Atualização de preços concluída!"))

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Erro no atualizador de preços: {err_msg}")
            self.after(0, lambda m=err_msg: messagebox.showerror("Erro", f"Erro ao atualizar preços:\n{m}"))

        finally:
            self.running = False
            self.after(0, self._ui_end)

    def _ui_end(self):
        self.btn_run.configure(state="normal")
        self.status_var.set("Pronto para atualizar preços")
        self.progress_var.set(0.0)