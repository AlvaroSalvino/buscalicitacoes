from .base import AdapterConfigError, AdapterError, BaseAdapter
from .pncp import PNCPAdapter
from .tcece import TCECEAdapter
from .tcema import TCEMAAdapter
from .tcepi import TCEPIAdapter

# Registry: chave = Fonte.tipo_adapter
ADAPTERS = {
    "pncp": PNCPAdapter,
    "tce_pi": TCEPIAdapter,
    "tce_ma": TCEMAAdapter,
    "tce_ce": TCECEAdapter,
}


def get_adapter(fonte) -> BaseAdapter:
    try:
        cls = ADAPTERS[fonte.tipo_adapter]
    except KeyError:
        raise AdapterConfigError(
            f"tipo_adapter '{fonte.tipo_adapter}' não registrado. "
            f"Disponíveis: {sorted(ADAPTERS)}"
        )
    return cls(config=fonte.config)


__all__ = [
    "ADAPTERS", "get_adapter", "BaseAdapter", "AdapterError", "AdapterConfigError",
]
