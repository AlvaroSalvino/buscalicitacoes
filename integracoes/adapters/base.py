"""
Contrato dos adapters de fontes externas.

Os adapters NÃO importam Django: recebem a config (dict) da Fonte e devolvem
DTOs simples. Quem grava no banco é integracoes/services.py. Isso mantém os
adapters testáveis sem banco e sem settings.

Os valores de `esfera`, `modalidade` e `status` dos DTOs são as mesmas strings
dos TextChoices de licitacoes.models (ex: "pregao", "aberta").
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, Optional


class AdapterError(Exception):
    """Falha transitória ao falar com a fonte (rede, 5xx, 429). Vale retry."""


class AdapterConfigError(Exception):
    """Config inválida da Fonte. Retry não resolve."""


@dataclass
class OrgaoDTO:
    cnpj: Optional[str]
    razao_social: str
    esfera: str
    uf: str
    municipio: str = ""


@dataclass
class LicitacaoDTO:
    id_externo: str
    orgao: OrgaoDTO
    objeto: str
    numero: str = ""
    modalidade: str = "outra"
    valor_estimado: Optional[Decimal] = None
    data_publicacao: Optional[date] = None
    # Datetimes "ingênuos" (horário de Brasília). O service os torna aware.
    data_abertura: Optional[datetime] = None
    data_encerramento_propostas: Optional[datetime] = None
    status: str = "publicada"
    link_original: str = ""
    uf: str = ""
    municipio: str = ""


class BaseAdapter(ABC):
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        # Fatias (ex: modalidade/UF) que falharam mesmo após retries. O service
        # lê isso ao final para decidir entre SUCESSO / PARCIAL / ERRO.
        self.erros: list[str] = []

    @abstractmethod
    def fetch(self, desde: Optional[datetime] = None) -> Iterator[dict]:
        """
        Gera registros brutos da fonte. `desde` é o início da janela
        incremental (None = primeira sincronização).
        """

    @abstractmethod
    def normalize(self, raw: dict) -> Optional[LicitacaoDTO]:
        """Converte um registro bruto em DTO, ou None se for inaproveitável."""
