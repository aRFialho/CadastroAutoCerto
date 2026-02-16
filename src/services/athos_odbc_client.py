from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class OdbcConfig:
    dsn: str
    user: str
    password: str
    role: Optional[str] = None
    charset: Optional[str] = None  # ex: "UTF8"


class AthosOdbcClient:
    """
    Cliente simples para Firebird via ODBC (DSN).
    - Usa pyodbc
    - Retorna lista de dicts (coluna -> valor)
    """

    def __init__(self, cfg: OdbcConfig):
        self.cfg = cfg

    def _build_conn_str(self) -> str:
        # DSN-based connection string
        parts = [
            f"DSN={self.cfg.dsn}",
            f"UID={self.cfg.user}",
            f"PWD={self.cfg.password}",
        ]
        if self.cfg.role:
            parts.append(f"ROLE={self.cfg.role}")
        if self.cfg.charset:
            parts.append(f"CHARSET={self.cfg.charset}")
        return ";".join(parts) + ";"

    def run_query(self, sql: str, timeout_seconds: int = 120) -> List[Dict[str, Any]]:
        """
        Executa SQL e retorna linhas como dicts.
        """
        try:
            import pyodbc  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "pyodbc não está instalado/configurado. "
                "Instale e garanta que o driver ODBC do Firebird esteja disponível."
            ) from e

        conn_str = self._build_conn_str()

        # autocommit para SELECT (evita locks)
        conn = pyodbc.connect(conn_str, autocommit=True)
        try:
            cur = conn.cursor()
            cur.timeout = timeout_seconds
            cur.execute(sql)

            col_names = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()

            out: List[Dict[str, Any]] = []
            for r in rows:
                # pyodbc.Row é indexável
                d = {col_names[i]: r[i] for i in range(len(col_names))}
                out.append(d)
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass


def normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza nomes de colunas para UPPER + sem espaços (opcional).
    Útil se o driver vier com nomes diferentes/variantes.
    """
    out: Dict[str, Any] = {}
    for k, v in row.items():
        nk = str(k).strip().upper()
        out[nk] = v
    return out
