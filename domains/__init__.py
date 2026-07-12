"""工程领域注册表。"""

from domains.registry import (
    DEFAULT_DOMAIN,
    DomainSpec,
    clear_domain_cache,
    list_domain_keys,
    load_domains,
    resolve_domain,
)

__all__ = [
    "DEFAULT_DOMAIN",
    "DomainSpec",
    "clear_domain_cache",
    "list_domain_keys",
    "load_domains",
    "resolve_domain",
]
