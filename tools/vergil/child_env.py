from __future__ import annotations

import os
import re
from typing import Mapping

_EXACT = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TZ", "TERM", "PWD",
        "TMPDIR", "TEMP", "TMP", "PYTHONPATH", "PYTHONHOME", "PYTHONUTF8", "PYTHONIOENCODING",
        "VIRTUAL_ENV", "NODE_PATH", "LD_LIBRARY_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "no_proxy", "all_proxy",
        "OPENROUTER_API_KEY", "OPENROUTER_OCR_API_KEY", "ANTHROPIC_API_KEY",
        "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET", "AZURE_CONFIG_DIR",
    }
)
_PREFIXES = (
    "LC_", "XDG_", "GOOSE_", "VERGIL_", "CASEFORGE_", "DOCUMENSO_", "GRAPH_", "SHAREPOINT_", "BUNDLETOOL_",
)
_SECRET_SHAPED = re.compile(
    r"PASSWORD|PASSPHRASE|SECRET|TOKEN|CREDENTIAL|PRIVATE|AUTHKEY|CONNECTION_STRING|DSN|PG_URL|API_KEY|COOKIE|BEARER|_KEY$|^KEY_"
)
EXTRA_ENV = "VERGIL_CHILD_ENV_EXTRA"


def child_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if source is None else source
    extra = {n.strip() for n in env.get(EXTRA_ENV, "").split(",") if n.strip()}
    kept: dict[str, str] = {}
    for name, value in env.items():
        if name in _EXACT or name in extra:
            kept[name] = value
        elif name.startswith(_PREFIXES) and not _SECRET_SHAPED.search(name.upper()):
            kept[name] = value
    return kept


MCP_SECRET_NEEDS: dict[str, tuple[str, ...]] = {
    "ops_mcp_server.py": (
        "CASEFORGE_CLIENTDB_PG_URL", "GRAPH_TENANT_ID", "GRAPH_MAILBOX_UPN", "GRAPH_MAIL_CLIENT_ID", "GRAPH_MAIL_CLIENT_SECRET",
        "GRAPH_FILES_CLIENT_ID", "GRAPH_FILES_CLIENT_SECRET", "CASEFORGE_QDRANT_URL", "CASEFORGE_QDRANT_READONLY_API_KEY",
        "CASEFORGE_QDRANT_API_KEY", "CASEFORGE_TELEMETRY_URL", "CASEFORGE_TELEMETRY_TOKEN", "OPENROUTER_API_KEY",
        "OPENROUTER_OCR_API_KEY",
    ),
    "documents_mcp_server.py": (
        "CASEFORGE_CLIENTDB_PG_URL", "GRAPH_TENANT_ID", "GRAPH_MAILBOX_UPN", "GRAPH_MAIL_CLIENT_ID", "GRAPH_MAIL_CLIENT_SECRET",
        "GRAPH_FILES_CLIENT_ID", "GRAPH_FILES_CLIENT_SECRET", "DOCUMENSO_API_TOKEN",
    ),
}
