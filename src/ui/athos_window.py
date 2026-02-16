from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from src.services.athos_whitelist import copy_whitelist_to_outputs, load_whitelist
from src.services.athos_odbc_client import AthosOdbcClient, OdbcConfig
from src.services.athos_sql import ATHOS_SQL_QUERY
from src.services.athos_rules_engine import process_rows
from src.services.athos_excel_generator import generate_rule_files
from src.services.athos_report_writer import write_report_xlsx


DEFAULT_CONFIG_PATHS = [
    Path("assets/config/settings.json"),
    Path("assets/settings.json"),
    Path("settings.json"),
]


def _now_tag() -> str:
    # ex: 2026-02-16_1430
    return datetime.now().strftime("%Y-%m-%d_%H%M")


def _find_config_path() -> Path:
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    # fallback: cria em settings.json
    return Path("settings.json")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class AthosWindow(ctk.CTkToplevel):
    """
    Tela separada: Robô Athos

    Fluxo:
    - Atualizar imediatos: seleciona arquivo -> copia para outputs/imediatos -> carrega whitelist -> salva no config
    - Gerar planilhas do dia: roda SQL via ODBC -> processa regras -> gera 5 xlsx -> gera relatório
    """

    def __init__(self, master, config_path: Optional[str | Path] = None):
        super().__init__(master)

        self.title("Robô Athos")
        self.geometry("860x560")
        self.minsize(820, 520)

        self.config_path = Path(config_path) if config_path else _find_config_path()
        self.cfg = _read_json(self.config_path)

        # seção athos no config
        self.cfg.setdefault("athos", {})
        self.cfg["athos"].setdefault("odbc_dsn", "EXCELREAD64")
        self.cfg["athos"].setdefault("odbc_user", "EXCEL_READ")
        self.cfg["athos"].setdefault("odbc_password", "172839")
        self.cfg["athos"].setdefault("odbc_role", "R_EXCEL")
        self.cfg["athos"].setdefault("template_path", "")  # você setará pelo botão
        self.cfg["athos"].setdefault("whitelist_path", "")  # preenchido ao atualizar
        self.cfg["athos"].setdefault("whitelist_updated_at", "")
        self.cfg["athos"].setdefault("outputs_dir", "outputs/robot")
        self.cfg["athos"].setdefault("report_dir", "outputs/robot/relatorios")

        self._build_ui()
        self._refresh_labels()

        # garante persistência do cfg inicial
        _write_json(self.config_path, self.cfg)

        # comportamento padrão de Toplevel
        self.transient(master)
        self.grab_set()
        self.focus()

    # ---------------- UI ----------------

    def _build_ui(self):
        pad = 12

        # Top bar
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=pad, pady=(pad, 6))

        self.lbl_cfg = ctk.CTkLabel(top, text="Config: -", anchor="w")
        self.lbl_cfg.pack(fill="x", padx=pad, pady=(8, 2))

        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=pad, pady=(4, 10))

        self.btn_template = ctk.CTkButton(
            row, text="Selecionar Template", command=self.on_select_template, width=180
        )
        self.btn_template.pack(side="left", padx=(0, 10))

        self.btn_whitelist = ctk.CTkButton(
            row, text="Atualizar imediatos", command=self.on_update_whitelist, width=180
        )
        self.btn_whitelist.pack(side="left", padx=(0, 10))

        self.btn_run = ctk.CTkButton(
            row, text="Gerar planilhas do dia", command=self.on_run, width=200
        )
        self.btn_run.pack(side="left", padx=(0, 10))

        self.btn_open_out = ctk.CTkButton(
            row, text="Abrir pasta outputs", command=self.on_open_outputs, width=180
        )
        self.btn_open_out.pack(side="left")

        # Status cards
        mid = ctk.CTkFrame(self)
        mid.pack(fill="x", padx=pad, pady=6)

        self.lbl_template = ctk.CTkLabel(mid, text="Template: -", anchor="w")
        self.lbl_template.pack(fill="x", padx=pad, pady=(10, 2))

        self.lbl_white = ctk.CTkLabel(mid, text="Whitelist: -", anchor="w")
        self.lbl_white.pack(fill="x", padx=pad, pady=(2, 10))

        # Log box
        bot = ctk.CTkFrame(self)
        bot.pack(fill="both", expand=True, padx=pad, pady=(6, pad))

        self.txt = ctk.CTkTextbox(bot, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=pad, pady=pad)

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt.insert("end", f"[{ts}] {msg}\n")
        self.txt.see("end")
        self.update_idletasks()

    def _refresh_labels(self):
        ath = self.cfg.get("athos", {})
        self.lbl_cfg.configure(text=f"Config: {self.config_path.as_posix()}")

        template = ath.get("template_path", "") or "-"
        self.lbl_template.configure(text=f"Template: {template}")

        wl = ath.get("whitelist_path", "") or "-"
        wl_at = ath.get("whitelist_updated_at", "") or "-"
        self.lbl_white.configure(text=f"Whitelist: {wl}  | Atualizada: {wl_at}")

    # ---------------- Actions ----------------

    def on_select_template(self):
        path = filedialog.askopenfilename(
            title="Selecione o template (XLSX)",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        self.cfg["athos"]["template_path"] = path
        _write_json(self.config_path, self.cfg)
        self._refresh_labels()
        self.log(f"Template selecionado: {path}")

    def on_update_whitelist(self):
        path = filedialog.askopenfilename(
            title="Selecione a whitelist de imediatos",
            filetypes=[
                ("Excel", "*.xls *.xlsx"),
                ("CSV", "*.csv"),
                ("TXT", "*.txt"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return

        try:
            self.log("Copiando whitelist para outputs/imediatos ...")
            dest = copy_whitelist_to_outputs(path)

            self.log("Carregando whitelist...")
            result = load_whitelist(dest)

            self.cfg["athos"]["whitelist_path"] = str(dest)
            self.cfg["athos"]["whitelist_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _write_json(self.config_path, self.cfg)

            self._refresh_labels()
            self.log(
                f"Whitelist OK: {result.valid_eans} EANs válidos | "
                f"duplicados ignorados: {result.duplicates_ignored} | inválidos: {result.invalid_ignored}"
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao atualizar whitelist:\n{e}")
            self.log(f"ERRO whitelist: {e}")

    def on_run(self):
        ath = self.cfg.get("athos", {})
        template_path = ath.get("template_path", "")
        whitelist_path = ath.get("whitelist_path", "")

        if not template_path or not Path(template_path).exists():
            messagebox.showwarning("Template", "Selecione o template primeiro (botão 'Selecionar Template').")
            return

        if not whitelist_path or not Path(whitelist_path).exists():
            messagebox.showwarning("Whitelist", "Atualize a whitelist primeiro (botão 'Atualizar imediatos').")
            return

        try:
            # 1) carrega whitelist
            self.log("Carregando whitelist...")
            wl = load_whitelist(whitelist_path).eans
            self.log(f"Whitelist carregada: {len(wl)} EANs")

            # 2) roda SQL via ODBC
            self.log("Conectando no ODBC e executando SQL...")
            cfg = OdbcConfig(
                dsn=ath.get("odbc_dsn", "EXCELREAD64"),
                user=ath.get("odbc_user", "EXCEL_READ"),
                password=ath.get("odbc_password", "172839"),
                role=ath.get("odbc_role", "R_EXCEL"),
            )
            client = AthosOdbcClient(cfg)
            rows = client.run_query(ATHOS_SQL_QUERY, timeout_seconds=180)
            self.log(f"SQL retornou {len(rows)} linhas")

            # 3) processa regras
            self.log("Processando regras (ordem oficial)...")
            outputs = process_rows(rows, wl)

            # 4) gera 5 planilhas
            out_dir = Path(ath.get("outputs_dir", "outputs/robot"))
            report_dir = Path(ath.get("report_dir", "outputs/robot/relatorios"))
            tag = _now_tag()

            self.log("Gerando 5 planilhas (aba PRODUTO)...")
            generated = generate_rule_files(
                template_path=template_path,
                out_dir=out_dir,
                actions_by_rule=outputs.actions_by_rule,
                date_tag=tag,
            )

            # 5) gera relatório único
            self.log("Gerando relatório único...")
            report_file = write_report_xlsx(outputs.report_lines, report_dir, date_tag=tag)

            # 6) resumo
            self.log("===== RESUMO =====")
            for rule, fp in generated.files_by_rule.items():
                qty = len(outputs.actions_by_rule.get(rule, []))
                self.log(f"{rule.value}: {qty} linhas -> {fp.as_posix()}")
            self.log(f"RELATÓRIO: {report_file.total_lines} linhas -> {report_file.path.as_posix()}")
            self.log("==================")

            messagebox.showinfo("Robô Athos", "Planilhas e relatório gerados com sucesso.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao gerar planilhas:\n{e}")
            self.log(f"ERRO run: {e}")

    def on_open_outputs(self):
        # abre pasta outputs/robot no explorer
        ath = self.cfg.get("athos", {})
        out_dir = Path(ath.get("outputs_dir", "outputs/robot"))

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            import os
            import platform
            import subprocess

            p = out_dir.resolve()

            if platform.system().lower().startswith("win"):
                os.startfile(str(p))  # type: ignore
            elif platform.system().lower() == "darwin":
                subprocess.run(["open", str(p)], check=False)
            else:
                subprocess.run(["xdg-open", str(p)], check=False)

            self.log(f"Abrindo pasta: {p.as_posix()}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não consegui abrir a pasta:\n{e}")
            self.log(f"ERRO abrir outputs: {e}")
