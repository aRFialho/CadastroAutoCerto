"""
Base do motor de regras do Robô Athos.

Responsável por:
- Normalizar linhas do export SQL para uma estrutura canônica
- Identificar entidades por linha: PA / KIT / PAI (podem existir ou não)
- Criar "grupo" (PA + KIT + PAI na mesma linha) e chaves de agrupamento por PAI
- Definir estruturas do relatório consolidado
- Helpers para:
  - normalização de strings
  - leitura segura de números (estoque)
  - dedupe de ações por EAN + tipo + regra

OBS:
- Não aplica regra de negócio ainda (isso entra nos próximos arquivos).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


class ItemType(str, Enum):
    PA = "PA"
    KIT = "KIT"
    PAI = "PAI"


class RuleKey(str, Enum):
    FORA_DE_LINHA = "FORA_DE_LINHA"
    ESTOQUE_COMPARTILHADO = "ESTOQUE_COMPARTILHADO"
    ENVIO_IMEDIATO = "ENVIO_IMEDIATO"
    SEM_GRUPO = "SEM_GRUPO"
    OUTLET = "OUTLET"


@dataclass(frozen=True)
class SqlTriple:
    """Representa 1 linha do SQL (PA + KIT + PAI na mesma linha)."""
    # PA
    pa_ean: Optional[str]
    pa_marca: Optional[str]
    pa_grupo3: Optional[str]
    pa_grupo: Optional[str]
    pa_estoque: Optional[float]
    pa_prazo: Optional[Any]

    # KIT
    kit_ean: Optional[str]
    kit_marca: Optional[str]
    kit_grupo: Optional[str]
    kit_estoque: Optional[float]
    kit_prazo: Optional[Any]

    # PAI
    pai_ean: Optional[str]
    pai_marca: Optional[str]
    pai_grupo: Optional[str]
    pai_prazo: Optional[Any]


@dataclass(frozen=True)
class ActionLine:
    """Linha do relatório consolidado."""
    ean: str
    item_type: ItemType
    marca: str
    grupo3: str
    action: str
    rule: RuleKey


@dataclass
class RuleOutput:
    """Saída acumulada de uma regra (linhas para escrever no Excel + linhas de relatório)."""
    # linhas para aba PRODUTOS (dict coluna->valor)
    rows: List[Dict[str, Any]]
    # linhas para relatório consolidado
    report: List[ActionLine]

    def __init__(self) -> None:
        self.rows = []
        self.report = []


# =========================
# Normalização / Helpers
# =========================

def norm_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s


def norm_upper(v: Any) -> str:
    return norm_str(v).upper()


def is_blank(v: Any) -> bool:
    return norm_str(v) == ""


def to_float(v: Any) -> Optional[float]:
    """
    Converte valores numéricos possivelmente vindos do Excel/Firebird:
    - "1.234,56" -> 1234.56
    - "10" -> 10.0
    - None/"" -> None
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm_str(v)
    if not s:
        return None
    # remove milhares e troca vírgula por ponto
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# =========================
# Parse SQL rows (dict) -> SqlTriple
# =========================

# chaves esperadas (baseadas no que você mandou)
SQL_KEYS = {
    # PA
    "pa_ean": ["codbarra_produto", "CODBARRA_PRODUTO"],
    "pa_marca": ["fabricante_produto", "FABRICANTE_PRODUTO"],
    "pa_grupo3": ["nome_grupo3", "NOME_GRUPO3"],
    "pa_grupo": ["nome_grupo", "NOME_GRUPO"],
    "pa_estoque": ["estoque_real_produto", "ESTOQUE_REAL_PRODUTO"],
    "pa_prazo": ["prazo_produto", "PRAZO_PRODUTO"],

    # KIT
    "kit_ean": ["codbarra_kit", "CODBARRA_KIT"],
    "kit_marca": ["fabricante_kit", "FABRICANTE_KIT"],
    "kit_grupo": ["nome_grupo_kit", "NOME_GRUPO_KIT", "NOME_GRUPO"],  # alguns exports repetem NOME_GRUPO
    "kit_estoque": ["estoque_real_kit", "ESTOQUE_REAL_KIT"],
    "kit_prazo": ["prazo_kit", "PRAZO_KIT"],

    # PAI
    "pai_ean": ["codbarra_pai", "CODBARRA_PAI"],
    "pai_marca": ["fabricante_pai", "FABRICANTE_PAI"],
    "pai_grupo": ["nome_grupo_pai", "NOME_GRUPO_PAI", "NOME_GRUPO"],
    "pai_prazo": ["prazo_pai", "PRAZO_PAI"],
}


def _pick(row: Dict[str, Any], candidates: List[str]) -> Any:
    # tenta match exato, depois case-insensitive
    if not row:
        return None

    # mapa normalizado
    keys = list(row.keys())
    norm_map = {norm_upper(k): k for k in keys}

    for c in candidates:
        if c in row:
            return row.get(c)
        cu = norm_upper(c)
        if cu in norm_map:
            return row.get(norm_map[cu])
    return None


def parse_sql_row(row: Dict[str, Any]) -> SqlTriple:
    pa_ean = norm_str(_pick(row, SQL_KEYS["pa_ean"])) or None
    pa_marca = norm_str(_pick(row, SQL_KEYS["pa_marca"])) or None
    pa_grupo3 = norm_str(_pick(row, SQL_KEYS["pa_grupo3"])) or None
    pa_grupo = norm_str(_pick(row, SQL_KEYS["pa_grupo"])) or None
    pa_estoque = to_float(_pick(row, SQL_KEYS["pa_estoque"]))
    pa_prazo = _pick(row, SQL_KEYS["pa_prazo"])

    kit_ean = norm_str(_pick(row, SQL_KEYS["kit_ean"])) or None
    kit_marca = norm_str(_pick(row, SQL_KEYS["kit_marca"])) or None
    kit_grupo = norm_str(_pick(row, SQL_KEYS["kit_grupo"])) or None
    kit_estoque = to_float(_pick(row, SQL_KEYS["kit_estoque"]))
    kit_prazo = _pick(row, SQL_KEYS["kit_prazo"])

    pai_ean = norm_str(_pick(row, SQL_KEYS["pai_ean"])) or None
    pai_marca = norm_str(_pick(row, SQL_KEYS["pai_marca"])) or None
    pai_grupo = norm_str(_pick(row, SQL_KEYS["pai_grupo"])) or None
    pai_prazo = _pick(row, SQL_KEYS["pai_prazo"])

    return SqlTriple(
        pa_ean=pa_ean,
        pa_marca=pa_marca,
        pa_grupo3=pa_grupo3,
        pa_grupo=pa_grupo,
        pa_estoque=pa_estoque,
        pa_prazo=pa_prazo,
        kit_ean=kit_ean,
        kit_marca=kit_marca,
        kit_grupo=kit_grupo,
        kit_estoque=kit_estoque,
        kit_prazo=kit_prazo,
        pai_ean=pai_ean,
        pai_marca=pai_marca,
        pai_grupo=pai_grupo,
        pai_prazo=pai_prazo,
    )


def parse_sql_export(sql_rows: List[Dict[str, Any]]) -> List[SqlTriple]:
    """
    Converte rows (dict) lidos do Excel do SQL export em lista de SqlTriple.
    """
    out: List[SqlTriple] = []
    for r in sql_rows:
        out.append(parse_sql_row(r))
    return out


# =========================
# Agrupamento por PAI (grupo do mesmo pai)
# =========================

def group_by_pai(triples: List[SqlTriple]) -> Dict[str, List[SqlTriple]]:
    """
    Agrupa por pai_ean.
    - Se pai_ean estiver vazio: agrupa em chave "__SEM_PAI__"
    """
    groups: Dict[str, List[SqlTriple]] = {}
    for t in triples:
        key = t.pai_ean or "__SEM_PAI__"
        groups.setdefault(key, []).append(t)
    return groups


def all_pas_in_group(triples: List[SqlTriple]) -> List[Tuple[str, Optional[float], Optional[str]]]:
    """
    Retorna lista de (pa_ean, pa_estoque, pa_marca) existentes no grupo.
    """
    out: List[Tuple[str, Optional[float], Optional[str]]] = []
    for t in triples:
        if t.pa_ean:
            out.append((t.pa_ean, t.pa_estoque, t.pa_marca))
    return out


# =========================
# Dedupe de ações (relatório)
# =========================

def action_key(a: ActionLine) -> str:
    return f"{a.ean}|{a.item_type.value}|{a.rule.value}|{a.action}".strip()


def dedupe_actions(actions: List[ActionLine]) -> List[ActionLine]:
    seen = set()
    out: List[ActionLine] = []
    for a in actions:
        k = action_key(a)
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out
