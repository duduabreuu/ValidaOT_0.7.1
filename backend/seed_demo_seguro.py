from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DB_FILE = ROOT / "validaot_dev_v013.db"
GENESIS_FILE = ROOT / "audit_dev_genesis.json"
SEED_FILE = ROOT / "seed_demo.py"

if Path.cwd().resolve() != ROOT:
    raise SystemExit("ERRO: execute o script dentro da pasta backend.")

if not ENV_FILE.is_file():
    raise SystemExit("ERRO: arquivo .env não encontrado.")

if not DB_FILE.is_file():
    raise SystemExit("ERRO: banco DEV não encontrado.")

if not GENESIS_FILE.is_file():
    raise SystemExit("ERRO: manifesto de auditoria não encontrado.")

if not SEED_FILE.is_file():
    raise SystemExit("ERRO: seed_demo.py não encontrado.")

load_dotenv(ENV_FILE, override=True)

if os.getenv("APP_ENV") != "development":
    raise SystemExit("ERRO: ambiente diferente de development.")

if os.getenv("DATABASE_URL") != "sqlite:///./validaot_dev_v013.db":
    raise SystemExit("ERRO: DATABASE_URL não corresponde ao banco DEV.")

password = os.getenv("DEMO_PASSWORD", "")

if not password or password.startswith("Change-This"):
    raise SystemExit("ERRO: DEMO_PASSWORD não configurada.")

import main
from audit_integrity_common import payload_sha256

if main.app.version != "0.7.0":
    raise SystemExit("ERRO: versão da API diferente de 0.7.0.")

actual_db = Path(main.engine.url.database)

if not actual_db.is_absolute():
    actual_db = (ROOT / actual_db).resolve()

if actual_db != DB_FILE.resolve():
    raise SystemExit("ERRO: backend direcionado para outro banco.")

if main.engine.dialect.name != "sqlite":
    raise SystemExit("ERRO: banco diferente de SQLite.")

manifest = json.loads(GENESIS_FILE.read_text(encoding="utf-8"))
payload = manifest.get("payload")
manifest_hash = manifest.get("sha256")

if not payload or not manifest_hash:
    raise SystemExit("ERRO: manifesto de auditoria inválido.")

if payload_sha256(payload) != manifest_hash:
    raise SystemExit("ERRO: hash do manifesto não confere.")

if payload.get("environment") != "development":
    raise SystemExit("ERRO: manifesto não pertence ao ambiente DEV.")

inspector = inspect(main.engine)

required_tables = [
    "companies",
    "users",
    "industrial_sites",
    "assets",
    "work_orders",
    "access_requests",
    "access_sessions",
    "audit_events",
    "audit_chain_state",
]

existing_tables = set(inspector.get_table_names())

missing = set(required_tables) - existing_tables

if missing:
    raise SystemExit(
        "ERRO: tabelas ausentes: " + ", ".join(sorted(missing))
    )

def get_counts(connection):
    return {
        table: connection.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()
        for table in required_tables
    }

with main.engine.connect() as connection:
    before = get_counts(connection)

    chain = connection.execute(
        text("""
            SELECT last_sequence, last_hash
            FROM audit_chain_state
            WHERE id = 1
        """)
    ).mappings().first()

if chain is None:
    raise SystemExit("ERRO: estado inicial da auditoria não encontrado.")

if chain["last_sequence"] != 0:
    raise SystemExit("ERRO: a cadeia já possui eventos.")

if chain["last_hash"] != manifest_hash:
    raise SystemExit("ERRO: âncora do banco diferente do manifesto.")

business_tables = [
    "companies",
    "users",
    "industrial_sites",
    "assets",
    "work_orders",
    "access_requests",
    "access_sessions",
    "audit_events",
]

for table in business_tables:
    if before[table] != 0:
        raise SystemExit(
            f"ERRO: tabela {table} já possui dados. Seed cancelado."
        )

if before["audit_chain_state"] != 1:
    raise SystemExit("ERRO: estado inicial da auditoria inesperado.")

print("PRE-VERIFICAÇÃO APROVADA.")
print("Banco:", actual_db)
print("Versão API:", main.app.version)
print("Âncora DEV:", manifest_hash)
print("Todas as tabelas de dados estão vazias.")

print("\nEXECUTANDO SEED DE DEMONSTRAÇÃO...")

subprocess.run(
    [sys.executable, str(SEED_FILE)],
    cwd=str(ROOT),
    check=True,
)

with main.engine.connect() as connection:
    after = get_counts(connection)

expected = {
    "companies": 2,
    "users": 5,
    "industrial_sites": 1,
    "assets": 4,
    "work_orders": 3,
    "access_requests": 0,
    "access_sessions": 0,
    "audit_events": 0,
}

for table, expected_count in expected.items():
    if after[table] != expected_count:
        raise RuntimeError(
            f"Quantidade inesperada em {table}: "
            f"{after[table]} (esperado: {expected_count})"
        )

print("\nSEED SEGURO CONCLUÍDO E CONFERIDO.")

for table, count in after.items():
    print(f"{table}: {count}")

print("\nBanco DEV:", actual_db)
print("A cadeia permanece na sequência inicial 0.")
