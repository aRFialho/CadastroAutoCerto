from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional
import re


class ItemTipo(str, Enum):
    PA = "PA"
    KIT = "KIT"
    PAI = "PAI"


class RuleName(str, Enum):
    FORA_DE_LINHA = "FORA DE LINHA"
    ESTOQUE_COMPARTILHADO = "ESTOQUE COMPARTILHADO"
    ENVIO_IMEDIATO = "ENVIO IMEDIATO"
    NENHUM_GRUPO = "NENHUM GRUPO"
    OUTLET = "OUTLET"


ORDERED_RULES: List[RuleName] = [
    RuleName.FORA_DE_LINHA,
    RuleName.ESTOQUE_COMPARTILHADO,
    RuleName.ENVIO_IMEDIATO,
    RuleName.NENHUM_GRUPO,
    RuleName.OUTLET,
]


@dataclass
class AthosRow:
    codbarra_produto: Optional[str] = None
    estoque_real_produto: Optional[float] = None
    prazo_produto: Optional[Any] = None
    fabricante_produto: Optional[str] = None
    nome_grupo3: Optional[str] = None

    nome_grupo_produto: Optional[str] = None

    codbarra_kit: Optional[str] = None
    estoque_real_kit: Optional[float] = None
    prazo_kit: Optional[Any] = None
    fabricante_kit: Optional[str] = None

    codbarra_pai: Optional[str] = None
    prazo_pai: Optional[Any] = None
    fabricante_pai: Optional[str] = None


@dataclass
class AthosAction:
    rule: RuleName
    tipo: ItemTipo
    codbarra: str

    grupo3: Optional[str] = None
    estoque_seguranca: Optional[int] = None
    produto_inativo: Optional[str] = None
    dias_entrega: Optional[int] = None
    site_disponibilidade: Optional[str] = None

    marca: Optional[str] = None
    grupo3_origem_pa: Optional[str] = None
    mensagens: List[str] = field(default_factory=list)

    def add_msg(self, msg: str) -> None:
        self.mensagens.append(msg)


@dataclass
class AthosReportLine:
    planilha: str
    codbarra: str
    tipo: str
    marca: str
    grupo3: str
    acao: str


def norm_text(v: Any) -> str:
    return str(v or "").strip()


def norm_upper(v: Any) -> str:
    return norm_text(v).upper()


def normalize_ean(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    s = re.sub(r"\D+", "", s)
    return s if s else None


def parse_int_safe(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    if s.strip().lower() == "imediata":
        return None
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    try:
        return int(float(s))
    except Exception:
        return None


def is_imediata(value: Any) -> bool:
    return norm_text(value).strip().lower() == "imediata"


def grupo3_bucket(nome_grupo3: Any) -> Optional[str]:
    g = norm_text(nome_grupo3)
    if not g:
        return None
    return g.strip().upper()


def apply_prazo(action: AthosAction, prazo_days: int) -> None:
    action.dias_entrega = int(prazo_days)
    action.site_disponibilidade = str(int(prazo_days))


def apply_imediata(action: AthosAction) -> None:
    action.dias_entrega = 0
    action.site_disponibilidade = "IMEDIATA"
