"""Visualizador de logs em tempo real com controle de parada"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import queue
from datetime import datetime
from typing import Optional

class RealTimeLogViewer:
    """Visualizador de logs em tempo real com controle"""

    def __init__(self, parent):
        self.parent = parent
        self.log_queue = queue.Queue()
        self.is_running = False
        self.update_thread = None
        self.window = None

        # ✅ CONTROLES DE PARADA
        self.should_stop = False
        self.force_close = False

        self.setup_window()
        self.start_log_processing()

    def setup_window(self):
        """Configura a janela de logs"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("📋 Logs do Sistema - Tempo Real")
        self.window.geometry("1000x600")

        # ✅ PROTOCOLO DE FECHAMENTO PERSONALIZADO
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Frame principal
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ✅ HEADER COM CONTROLES
        header_frame = ctk.CTkFrame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        # Título
        title_label = ctk.CTkLabel(
            header_frame,
            text="📋 Logs do Sistema em Tempo Real",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(side="left", padx=10, pady=10)

        # ✅ BOTÕES DE CONTROLE
        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.pack(side="right", padx=10, pady=5)

        self.pause_btn = ctk.CTkButton(
            controls_frame,
            text="⏸️ Pausar",
            command=self.toggle_pause,
            width=100,
            height=30
        )
        self.pause_btn.pack(side="left", padx=5)

        self.clear_btn = ctk.CTkButton(
            controls_frame,
            text="🗑️ Limpar",
            command=self.clear_logs,
            width=100,
            height=30
        )
        self.clear_btn.pack(side="left", padx=5)

        self.stop_btn = ctk.CTkButton(
            controls_frame,
            text="⏹️ Parar",
            command=self.stop_logging,
            width=100,
            height=30,
            fg_color="red",
            hover_color="darkred"
        )
        self.stop_btn.pack(side="left", padx=5)

        self.close_btn = ctk.CTkButton(
            controls_frame,
            text="❌ Fechar",
            command=self.force_close_window,
            width=100,
            height=30,
            fg_color="gray",
            hover_color="darkgray"
        )
        self.close_btn.pack(side="left", padx=5)

        # ✅ STATUS BAR
        self.status_frame = ctk.CTkFrame(main_frame)
        self.status_frame.pack(fill="x", pady=(0, 5))

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="🟢 Capturando logs...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="left", padx=10, pady=5)

        self.log_count_label = ctk.CTkLabel(
            self.status_frame,
            text="📊 Logs: 0",
            font=ctk.CTkFont(size=12)
        )
        self.log_count_label.pack(side="right", padx=10, pady=5)

        # Área de texto para logs
        text_frame = ctk.CTkFrame(main_frame)
        text_frame.pack(fill="both", expand=True)

        self.text_area = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#404040"
        )

        # Scrollbar
        scrollbar = tk.Scrollbar(text_frame, command=self.text_area.yview)
        self.text_area.config(yscrollcommand=scrollbar.set)

        self.text_area.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", pady=10, padx=(0, 10))

        # ✅ CONFIGURAR CORES PARA DIFERENTES NÍVEIS
        self.text_area.tag_config("INFO", foreground="#00ff00")
        self.text_area.tag_config("SUCCESS", foreground="#00ff00", font=("Consolas", 10, "bold"))
        self.text_area.tag_config("WARNING", foreground="#ffff00")
        self.text_area.tag_config("ERROR", foreground="#ff0000")
        self.text_area.tag_config("DEBUG", foreground="#888888")
        self.text_area.tag_config("CRITICAL", foreground="#ff0000", font=("Consolas", 10, "bold"))

        # ✅ CONTADOR DE LOGS
        self.log_count = 0

    def start_log_processing(self):
        """Inicia o processamento de logs"""
        self.is_running = True
        self.should_stop = False
        self.update_thread = threading.Thread(target=self.process_log_queue, daemon=True)
        self.update_thread.start()

    def process_log_queue(self):
        """Processa a fila de logs em thread separada"""
        while self.is_running and not self.should_stop:
            try:
                # ✅ TIMEOUT PARA PERMITIR PARADA
                log_entry = self.log_queue.get(timeout=0.5)

                if not self.should_stop and self.window and self.window.winfo_exists():
                    # Atualizar UI na thread principal
                    self.window.after(0, lambda entry=log_entry: self.update_text_area(entry))

                self.log_queue.task_done()

            except queue.Empty:
                # ✅ TIMEOUT - VERIFICAR SE DEVE PARAR
                continue
            except Exception as e:
                print(f"Erro no processamento de logs: {e}")
                break

        # ✅ ATUALIZAR STATUS QUANDO PARAR
        if self.window and self.window.winfo_exists():
            self.window.after(0, self.update_stopped_status)

    def update_text_area(self, log_entry):
        """Atualiza a área de texto com novo log"""
        try:
            if not self.window or not self.window.winfo_exists():
                return

            level, message, module, timestamp = log_entry

            # ✅ VERIFICAR SE DEVE PARAR
            if self.should_stop:
                return

            # Formatar log
            formatted_log = f"[{timestamp}] [{level}] [{module}] {message}\n"

            # Inserir no final
            self.text_area.insert(tk.END, formatted_log, level)

            # ✅ LIMITAR NÚMERO DE LINHAS PARA PERFORMANCE
            lines = int(self.text_area.index('end-1c').split('.')[0])
            if lines > 1000:  # Manter apenas últimas 1000 linhas
                self.text_area.delete('1.0', '500.0')  # Remove primeiras 500

            # Auto-scroll
            self.text_area.see(tk.END)

            # ✅ ATUALIZAR CONTADOR
            self.log_count += 1
            self.log_count_label.configure(text=f"📊 Logs: {self.log_count}")

        except Exception as e:
            print(f"Erro ao atualizar área de texto: {e}")

    def add_log(self, level: str, message: str, module: str, timestamp: Optional[str] = None):
        """Adiciona log à fila"""
        try:
            if self.should_stop:
                return

            if not timestamp:
                timestamp = datetime.now().strftime("%H:%M:%S")

            self.log_queue.put((level, message, module, timestamp))
        except Exception as e:
            print(f"Erro ao adicionar log: {e}")

    # ✅ MÉTODOS DE CONTROLE
    def toggle_pause(self):
        """Pausa/retoma captura de logs"""
        if self.is_running:
            self.is_running = False
            self.pause_btn.configure(text="▶️ Retomar")
            self.status_label.configure(text="⏸️ Pausado")
        else:
            self.is_running = True
            self.pause_btn.configure(text="⏸️ Pausar")
            self.status_label.configure(text="🟢 Capturando logs...")
            # Reiniciar thread se necessário
            if not self.update_thread or not self.update_thread.is_alive():
                self.start_log_processing()

    def clear_logs(self):
        """Limpa todos os logs"""
        try:
            self.text_area.delete('1.0', tk.END)
            self.log_count = 0
            self.log_count_label.configure(text="📊 Logs: 0")
        except Exception as e:
            print(f"Erro ao limpar logs: {e}")

    def stop_logging(self):
        """Para completamente a captura de logs"""
        self.should_stop = True
        self.is_running = False
        self.status_label.configure(text="⏹️ Parado")
        self.pause_btn.configure(text="▶️ Retomar", state="disabled")
        self.stop_btn.configure(text="✅ Parado", state="disabled")

    def update_stopped_status(self):
        """Atualiza status quando parado"""
        try:
            if self.window and self.window.winfo_exists():
                self.status_label.configure(text="⏹️ Captura de logs interrompida")
        except Exception:
            pass

    def force_close_window(self):
        """Força fechamento da janela"""
        self.force_close = True
        self.on_closing()

    def on_closing(self):
        """Callback quando janela é fechada"""
        try:
            if not self.force_close and self.is_running:
                # ✅ PERGUNTAR SE QUER FECHAR MESMO COM LOGS RODANDO
                result = messagebox.askyesno(
                    "Fechar Logs",
                    "Os logs ainda estão sendo capturados.\n\n"
                    "Deseja realmente fechar a janela?\n"
                    "(Os logs continuarão sendo processados em segundo plano)"
                )
                if not result:
                    return

            # ✅ PARAR CAPTURA DE LOGS
            self.should_stop = True
            self.is_running = False

            # ✅ AGUARDAR THREAD TERMINAR (COM TIMEOUT)
            if self.update_thread and self.update_thread.is_alive():
                self.update_thread.join(timeout=2.0)  # Aguarda no máximo 2 segundos

            # ✅ FECHAR JANELA
            if self.window and self.window.winfo_exists():
                self.window.destroy()

        except Exception as e:
            print(f"Erro ao fechar janela de logs: {e}")
            # ✅ FORÇA FECHAMENTO EM CASO DE ERRO
            try:
                if self.window:
                    self.window.destroy()
            except Exception:
                pass

    def show(self):
        """Mostra a janela"""
        try:
            if self.window and self.window.winfo_exists():
                self.window.lift()
                self.window.focus()
        except Exception as e:
            print(f"Erro ao mostrar janela: {e}")