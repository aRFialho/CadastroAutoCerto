"""Serviço de envio de e-mails"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ..core.models import EmailConfig, ProcessingResult
from ..utils.logger import get_logger
from ..core.exceptions import EmailSendError

logger = get_logger("email_sender")

class EmailSender:
    """Serviço para envio de e-mails"""

    def __init__(self, config: EmailConfig):
        self.config = config

    async def send_processing_report(
        self,
        result: ProcessingResult,
        origin_file: Path,
        subject_prefix: str = "[Cadastro Automático]"
    ) -> bool:
        """Envia relatório de processamento por e-mail"""

        try:
            logger.info("📧 Preparando e-mail de relatório...")

            # Gera conteúdo do e-mail
            subject = f"{subject_prefix} Processamento Concluído - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            html_content = self._generate_report_html(result, origin_file)

            # Cria mensagem
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config.from_addr
            msg['To'] = ", ".join(self.config.to_addrs)
            msg['Subject'] = subject

            # Adiciona conteúdo HTML
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)

            # Anexa arquivo se existir e for bem-sucedido
            if result.success and result.output_file and result.output_file.exists():
                self._attach_file(msg, result.output_file)

            # Envia e-mail
            await self._send_email(msg)

            logger.success(f"✅ E-mail enviado com sucesso para: {', '.join(self.config.to_addrs)}")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao enviar e-mail: {e}")
            raise EmailSendError(f"Falha no envio: {e}")

    def _generate_report_html(self, result: ProcessingResult, origin_file: Path) -> str:
        """Gera conteúdo HTML do relatório"""

        # Status e ícone
        if result.success:
            status_icon = "✅"
            status_text = "SUCESSO"
            status_color = "#28a745"
        else:
            status_icon = "❌"
            status_text = "ERRO"
            status_color = "#dc3545"

        # Calcula taxa de sucesso
        success_rate = result.success_rate * 100 if result.success_rate else 0

        # Template HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .status {{ background: {status_color}; color: white; padding: 15px; text-align: center; font-weight: bold; font-size: 18px; }}
                .content {{ padding: 30px; }}
                .stats {{ display: flex; justify-content: space-between; margin: 20px 0; }}
                .stat {{ text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; flex: 1; margin: 0 5px; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #495057; }}
                .stat-label {{ font-size: 12px; color: #6c757d; text-transform: uppercase; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .info-table th, .info-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
                .info-table th {{ background-color: #e9ecef; font-weight: bold; }}
                .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 12px; }}
                .error-list {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 15px; margin: 15px 0; }}
                .error-list h4 {{ color: #721c24; margin-top: 0; }}
                .error-item {{ color: #721c24; margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏭 D'Rossi - Cadastro Automático</h1>
                    <p>Relatório de Processamento de Produtos</p>
                </div>
                
                <div class="status">
                    {status_icon} {status_text}
                </div>
                
                <div class="content">
                    <h2>📊 Resumo do Processamento</h2>
                    
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-number">{result.total_products}</div>
                            <div class="stat-label">Produtos</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{result.total_variations}</div>
                            <div class="stat-label">Variações</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{result.total_kits}</div>
                            <div class="stat-label">Kits</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{success_rate:.1f}%</div>
                            <div class="stat-label">Sucesso</div>
                        </div>
                    </div>
                    
                    <table class="info-table">
                        <tr>
                            <th>📁 Arquivo de Origem</th>
                            <td>{origin_file.name}</td>
                        </tr>
                        <tr>
                            <th>📄 Arquivo Gerado</th>
                            <td>{result.output_file.name if result.output_file else 'N/A'}</td>
                        </tr>
                        <tr>
                            <th>⏱️ Tempo de Processamento</th>
                            <td>{result.processing_time:.2f} segundos</td>
                        </tr>
                        <tr>
                            <th>📅 Data/Hora</th>
                            <td>{datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</td>
                        </tr>
                    </table>
                    
                    {self._generate_errors_section(result.errors) if result.errors else ''}
                    
                    <h3>📋 Abas Processadas:</h3>
                    <ul>
                        <li><strong>PRODUTO:</strong> {result.total_products} registros</li>
                        <li><strong>VARIACAO:</strong> {result.total_variations} registros</li>
                        <li><strong>LOJA WEB:</strong> {result.total_products} registros</li>
                        <li><strong>KIT:</strong> {result.total_kits} registros</li>
                        <li><strong>Instruções de Preenchimento:</strong> Copiada da origem</li>
                        <li><strong>Tipo Importação:</strong> Copiada da origem</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>Este e-mail foi gerado automaticamente pelo sistema de Cadastro de Produtos D'Rossi</p>
                    <p>Desenvolvido com ❤️ para otimizar seus processos</p>
                    <p>Made By: Alan Raphael, with 2025 ❤ </p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _generate_errors_section(self, errors: List[str]) -> str:
        """Gera seção de erros se houver"""
        if not errors:
            return ""

        error_items = "".join([f'<div class="error-item">• {error}</div>' for error in errors])

        return f"""
        <div class="error-list">
            <h4>⚠️ Erros Encontrados:</h4>
            {error_items}
        </div>
        """

    def _attach_file(self, msg: MIMEMultipart, file_path: Path):
        """Anexa arquivo ao e-mail"""
        try:
            with open(file_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())

            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {file_path.name}'
            )

            msg.attach(part)
            logger.info(f"📎 Arquivo anexado: {file_path.name}")

        except Exception as e:
            logger.warning(f"⚠️ Erro ao anexar arquivo: {e}")

    async def _send_email(self, msg: MIMEMultipart):
        """Envia o e-mail via SMTP - CORRIGIDO"""
        try:
            # Cria contexto SSL
            context = ssl.create_default_context()

            # CORRIGIDO: Usa SMTP_SSL diretamente para Gmail
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, context=context) as server:
                # Login
                server.login(self.config.username, self.config.password)

                # Envia e-mail
                text = msg.as_string()
                server.sendmail(
                    self.config.from_addr,
                    self.config.to_addrs,
                    text
                )

                logger.info("📧 E-mail enviado via SMTP")

        except Exception as e:
            logger.error(f"❌ Erro SMTP: {e}")
            raise EmailSendError(f"Falha SMTP: {e}")

    def test_connection(self) -> bool:
        """Testa conexão SMTP - CORRIGIDO"""
        try:
            context = ssl.create_default_context()

            # CORRIGIDO: Usa SMTP_SSL diretamente
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, context=context) as server:
                server.login(self.config.username, self.config.password)

            logger.success("✅ Conexão SMTP testada com sucesso")
            return True

        except Exception as e:
            logger.error(f"❌ Erro no teste SMTP: {e}")
            return False