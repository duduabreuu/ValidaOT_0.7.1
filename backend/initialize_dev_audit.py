from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DB_FILE = ROOT / "validaot_dev_v013.db"
MANIFEST_FILE = ROOT / "audit_dev_genesis.json"

if Path.cwd().resolve() != ROOT:
    raise SystemExit("ERRO: execute o script dentro da pasta DEV.")

if not ENV_FILE.is_file():
    raise SystemExit("ERRO: .env DEV não encontrado.")

if DB_FILE.exists() or MANIFEST_FILE.exists():
    raise SystemExit("ERRO: banco ou manifesto já existente. Inicialização cancelada.")

load_dotenv(ENV_FILE, override=True)

expected_url = "sqlite:///./validaot_dev_v013.db"

if os.getenv("DATABASE_URL") != expected_url:
    raise SystemExit("ERRO: DATABASE_URL não corresponde ao banco DEV.")

if os.getenv("APP_ENV") != "development":
    raise SystemExit("ERRO: ambiente diferente de development.")

if len(os.getenv("JWT_SECRET_KEY", "")) < 32:
    raise SystemExit("ERRO: chave JWT inválida.")

Fernet(os.environ["MFA_ENCRYPTION_KEY"].encode("ascii"))

from audit_integrity_common import payload_sha256
from main import (
    app,
    Base,
    engine,
    SessionLocal,
    AuditChainState,
    AuditEvent,
    utcnow,
    _validate_config,
)

if app.version != "0.7.0":
    raise SystemExit("ERRO: versão do backend diferente de 0.7.0.")

actual_db = Path(engine.url.database)
if not actual_db.is_absolute():
    actual_db = (ROOT / actual_db).resolve()

if actual_db != DB_FILE.resolve():
    raise SystemExit("ERRO: engine direcionado para banco diferente do DEV.")

_validate_config()

# Cria o esquema completo somente no banco DEV recém-verificado.
Base.metadata.create_all(bind=engine)

created_at = datetime.now(timezone.utc).isoformat()

genesis_payload = {
    "format": "validaot-dev-audit-genesis-v1",
    "application": "ValidaOT API",
    "api_version": "0.7.0",
    "environment": "development",
    "database": DB_FILE.name,
    "anchor_event_count": 0,
    "created_at_utc": created_at,
    "origin": "isolated development environment; not a production baseline",
}

genesis_hash = payload_sha256(genesis_payload)

db = SessionLocal()

try:
    if db.get(AuditChainState, 1) is not None:
        raise RuntimeError("Estado de auditoria inesperadamente existente.")

    if db.query(AuditEvent).count() != 0:
        raise RuntimeError("Banco DEV contém eventos inesperados.")

    state = AuditChainState(
        id=1,
        last_sequence=0,
        last_hash=genesis_hash,
        anchor_event_count=0,
        anchor_hash=genesis_hash,
        updated_at=utcnow(),
    )

    db.add(state)
    db.commit()

except Exception:
    db.rollback()
    raise

finally:
    db.close()

manifest = {
    "payload": genesis_payload,
    "sha256": genesis_hash,
}

temporary_manifest = MANIFEST_FILE.with_suffix(".json.tmp")

temporary_manifest.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

temporary_manifest.replace(MANIFEST_FILE)

print("CADEIA DE AUDITORIA DEV INICIALIZADA.")
print("Versão API:", app.version)
print("Eventos iniciais: 0")
print("Sequência inicial: 0")
print("Âncora DEV SHA-256:", genesis_hash)
print("Banco DEV:", DB_FILE.resolve())
print("Manifesto:", MANIFEST_FILE.resolve())
print("Baseline oficial: NÃO UTILIZADO")
