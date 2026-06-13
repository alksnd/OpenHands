import os
import re


MANAGED_LITELLM_MODELS_ENV = 'OPENHANDS_MANAGED_LITELLM_MODELS'
_MODEL_ENTRY_SPLIT_RE = re.compile(r'[,\n\r]+')


def parse_managed_litellm_model_aliases(raw_value: str | None) -> list[str]:
    """Parse operator-configured LiteLLM model entries into route aliases.

    The raw value comes from OHE/KOTS and accepts comma or newline separated
    entries. Each entry may be either ``model-id`` or ``alias=model-id``. The
    alias is the stable LiteLLM route name surfaced in OpenHands as
    ``openhands/<alias>``.
    """
    if not raw_value:
        return []

    aliases: list[str] = []
    seen: set[str] = set()
    for raw_entry in _MODEL_ENTRY_SPLIT_RE.split(raw_value):
        entry = raw_entry.strip()
        if not entry:
            continue

        if '=' in entry:
            alias, model_id = (part.strip() for part in entry.split('=', 1))
            if not alias or not model_id:
                continue
        else:
            alias = entry

        alias = alias.removeprefix('openhands/').removeprefix('litellm_proxy/')
        if not alias or alias in seen:
            continue
        aliases.append(alias)
        seen.add(alias)

    return aliases


def get_managed_litellm_model_aliases() -> list[str]:
    return parse_managed_litellm_model_aliases(
        os.getenv(MANAGED_LITELLM_MODELS_ENV)
    )


def get_managed_openhands_models() -> list[str]:
    return [f'openhands/{alias}' for alias in get_managed_litellm_model_aliases()]
