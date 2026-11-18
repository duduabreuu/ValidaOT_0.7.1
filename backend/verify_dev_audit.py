from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from audit_integrity_common import EVENT_FIELDS, compute_event_hash, payload_sha256

ROOT = Path(__file__).resolve().parent
DB_FILE = ROOT / "validaot_dev_v013.db"
MANIFEST_FILE = ROOT / "audit_dev_genesis.json"


def fail(message: str) -> None:
    raise SystemExit(f"FALHA DE INTEGRIDADE DEV: {message}")


def main() -> None:
    if not DB_FILE.is_file():
        fail(f"Banco DEV não encontrado: {DB_FILE}")

    if not MANIFEST_FILE.is_file():
        fail("Manifesto de gênese DEV não encontrado.")

    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        payload = manifest["payload"]
        expected_genesis_hash = str(manifest["sha256"]).lower()
    except Exception as exc:
        fail(f"Manifesto inválido: {exc}")

    if payload.get("format") != "validaot-dev-audit-genesis-v1":
        fail("Formato de gênese inesperado.")

    if payload.get("environment") != "development":
        fail("Manifesto não identifica o ambiente development.")

    if payload.get("database") != DB_FILE.name:
        fail("Manifesto aponta para outro banco.")

    if payload.get("anchor_event_count") != 0:
        fail("Gênese DEV deve começar sem eventos históricos.")

    calculated_genesis_hash = payload_sha256(payload)

    if calculated_genesis_hash != expected_genesis_hash:
        fail("Hash do manifesto de gênese não confere.")

    db_uri = DB_FILE.resolve().as_uri() + "?mode=ro"

    try:
        with sqlite3.connect(db_uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row

            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                fail(f"PRAGMA integrity_check: {integrity}")

            columns = (
                list(EVENT_FIELDS)
                + ["chain_sequence", "previous_hash", "event_hash"]
            )

            query = "SELECT " + ", ".join(columns) + " FROM audit_events"
            rows = [dict(row) for row in conn.execute(query).fetchall()]

            ids = [str(row["id"]) for row in rows]
            if len(ids) != len(set(ids)):
                fail("IDs duplicados na tabela audit_events.")

            for row in rows:
                if (
                    row["chain_sequence"] is None
                    or not row["previous_hash"]
                    or not row["event_hash"]
                ):
                    fail(f"Evento sem encadeamento: {row['id']}")

            chained = sorted(
                rows,
                key=lambda row: int(row["chain_sequence"]),
            )

            state_rows = conn.execute(
                "SELECT * FROM audit_chain_state ORDER BY id"
            ).fetchall()

            if len(state_rows) != 1 or int(state_rows[0]["id"]) != 1:
                fail("Estado da cadeia ausente ou duplicado.")

            state = dict(state_rows[0])

            if int(state["anchor_event_count"]) != 0:
                fail("Quantidade de eventos âncora divergente.")

            if state["anchor_hash"] != calculated_genesis_hash:
                fail("Hash âncora do banco diverge do manifesto DEV.")

            expected_sequence = 1
            previous_hash = calculated_genesis_hash

            seen_sequences = set()

            for row in chained:
                sequence = int(row["chain_sequence"])

                if sequence in seen_sequences:
                    fail(f"Sequência duplicada: {sequence}")

                seen_sequences.add(sequence)

                if sequence != expected_sequence:
                    fail(
                        f"Sequência quebrada: esperada {expected_sequence}, "
                        f"encontrada {sequence}."
                    )

                if row["previous_hash"] != previous_hash:
                    fail(f"previous_hash divergente no evento {row['id']}.")

                calculated_hash = compute_event_hash(
                    sequence,
                    previous_hash,
                    row,
                )

                if row["event_hash"] != calculated_hash:
                    fail(f"event_hash divergente no evento {row['id']}.")

                previous_hash = calculated_hash
                expected_sequence += 1

            expected_last_sequence = len(chained)

            if int(state["last_sequence"]) != expected_last_sequence:
                fail("last_sequence diverge da quantidade de eventos.")

            if state["last_hash"] != previous_hash:
                fail("last_hash diverge da cabeça calculada da cadeia.")

            print("VERIFICACAO DE INTEGRIDADE DEV: OK")
            print(f"Banco: {DB_FILE.resolve()}")
            print(f"Eventos verificados: {len(chained)}")
            print(f"Eventos de gênese: 0")
            print(f"Última sequência: {state['last_sequence']}")
            print(f"Hash âncora DEV: {calculated_genesis_hash}")
            print(f"Cabeça atual da cadeia: {previous_hash}")
            print("Modo: somente leitura; banco não foi alterado.")
            print("Baseline oficial: NÃO UTILIZADO.")

    except sqlite3.Error as exc:
        fail(f"Erro SQLite: {exc}")


if __name__ == "__main__":
    main()
