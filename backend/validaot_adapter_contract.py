"""ValidaOT adapter contract and in-memory simulator for the academic MVP.

This module never opens a network connection and never communicates with SCADA, HMI,
engineering stations, or PLCs. It represents the contract that a future vendor-specific
adapter could implement. The application backend must perform authoritative RBAC,
work-order, MFA and approval validation before invoking grant_session().
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from enum import Enum
from hashlib import sha256
import json
from typing import Dict, Optional, Protocol, Tuple


class AccessProfile(str, Enum):
    READ_ONLY = "READ_ONLY"
    DIAGNOSTIC = "DIAGNOSTIC"
    MAINTENANCE = "MAINTENANCE"


class TargetStatus(str, Enum):
    KNOWN_AVAILABLE = "KNOWN_AVAILABLE"
    KNOWN_UNAVAILABLE = "KNOWN_UNAVAILABLE"
    UNKNOWN_TARGET = "UNKNOWN_TARGET"


class SessionStatus(str, Enum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    REVOKING = "REVOKING"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class AdapterError:
    code: str
    message: str
    retryable: bool = False


class AdapterContractError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.error = AdapterError(code=code, message=message, retryable=retryable)


@dataclass(frozen=True)
class HealthResult:
    status: str  # AVAILABLE or UNAVAILABLE
    provider: str = "SIMULATED"


@dataclass(frozen=True)
class TargetCheckResult:
    target_ref: str
    status: TargetStatus
    provider: str = "SIMULATED"


@dataclass(frozen=True)
class GrantSessionCommand:
    request_id: str
    idempotency_key: str
    asset_id: str
    gateway_ref: str
    user_id: str
    external_identity_ref: str
    work_order_id: str
    work_order_code: str
    access_profile: AccessProfile
    valid_from: datetime
    expires_at: datetime
    mfa_verified_at: datetime
    requires_dual_approval: bool
    approval_ids: Tuple[str, ...]
    correlation_id: str


@dataclass
class SessionResult:
    status: SessionStatus
    provider: str
    external_session_id: str
    request_id: str
    asset_id: str
    user_id: str
    work_order_id: str
    access_profile: AccessProfile
    started_at: datetime
    expires_at: datetime
    correlation_id: str
    closed_at: Optional[datetime] = None
    status_reason: Optional[str] = None


class AccessAdapter(Protocol):
    def health_check(self) -> HealthResult: ...
    def check_target(self, target_ref: str) -> TargetCheckResult: ...
    def grant_session(self, command: GrantSessionCommand) -> SessionResult: ...
    def get_session(self, session_id: str) -> SessionResult: ...
    def revoke_session(self, session_id: str, reason: str, idempotency_key: str) -> SessionResult: ...


def _ensure_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AdapterContractError("INVALID_WINDOW", f"{field} deve conter fuso horário.")


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _fingerprint(command: GrantSessionCommand) -> str:
    payload = {
        "request_id": command.request_id,
        "asset_id": command.asset_id,
        "gateway_ref": command.gateway_ref,
        "user_id": command.user_id,
        "work_order_id": command.work_order_id,
        "access_profile": command.access_profile.value,
        "valid_from": _as_utc(command.valid_from).isoformat(),
        "expires_at": _as_utc(command.expires_at).isoformat(),
        "mfa_verified_at": _as_utc(command.mfa_verified_at).isoformat(),
        "requires_dual_approval": command.requires_dual_approval,
        "approval_ids": sorted(command.approval_ids),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class SimulatedAccessAdapter:
    """In-memory, vendor-neutral session simulator; no network or hardware access."""

    def __init__(
        self,
        targets: Optional[Dict[str, bool]] = None,
        mfa_freshness: timedelta = timedelta(minutes=10),
        max_session_duration: timedelta = timedelta(minutes=120),
    ) -> None:
        # target reference -> available flag
        self._targets = dict(targets or {
            "SIM-ENG-01": True,
            "SIM-SCADA-01": True,
            "SIM-HMI-01": True,
            "SIM-PLC-01": True,
        })
        self._mfa_freshness = mfa_freshness
        self._max_session_duration = max_session_duration
        self._available = True
        self._sessions: Dict[str, SessionResult] = {}
        self._request_sessions: Dict[str, str] = {}  # one session per request in the MVP
        self._idempotency: Dict[str, tuple[str, str]] = {}  # key -> (fingerprint, session id)
        self._revoke_keys: Dict[str, str] = {}  # key -> session id
        self._counter = 0

    def health_check(self) -> HealthResult:
        return HealthResult("AVAILABLE" if self._available else "UNAVAILABLE")

    def set_available(self, available: bool) -> None:
        """Test hook to simulate adapter outage."""
        self._available = bool(available)

    def set_target_available(self, target_ref: str, available: bool) -> None:
        """Test hook to simulate an unavailable configured asset."""
        if target_ref not in self._targets:
            raise AdapterContractError("UNKNOWN_TARGET", "Referência de ativo desconhecida.")
        self._targets[target_ref] = bool(available)

    def check_target(self, target_ref: str) -> TargetCheckResult:
        if not self._available:
            raise AdapterContractError("ADAPTER_UNAVAILABLE", "Adaptador simulado indisponível.", True)
        if target_ref not in self._targets:
            return TargetCheckResult(target_ref, TargetStatus.UNKNOWN_TARGET)
        status = TargetStatus.KNOWN_AVAILABLE if self._targets[target_ref] else TargetStatus.KNOWN_UNAVAILABLE
        return TargetCheckResult(target_ref, status)

    def grant_session(self, command: GrantSessionCommand) -> SessionResult:
        self._validate_command(command)
        fp = _fingerprint(command)
        # Idempotency lookup comes first: a retry of a completed command must return
        # its prior result even if the simulated target or adapter is now unavailable.
        if command.idempotency_key in self._idempotency:
            old_fp, session_id = self._idempotency[command.idempotency_key]
            if old_fp != fp:
                raise AdapterContractError("IDEMPOTENCY_CONFLICT", "A chave idempotente já foi usada com outro conteúdo.")
            return self.get_session(session_id)
        if not self._available:
            raise AdapterContractError("ADAPTER_UNAVAILABLE", "Adaptador simulado indisponível.", True)
        target = self.check_target(command.gateway_ref)
        if target.status == TargetStatus.UNKNOWN_TARGET:
            raise AdapterContractError("UNKNOWN_TARGET", "Referência do ativo não cadastrada no adaptador.")
        if target.status == TargetStatus.KNOWN_UNAVAILABLE:
            raise AdapterContractError("TARGET_UNAVAILABLE", "Ativo indisponível no adaptador simulado.", True)
        if command.request_id in self._request_sessions:
            raise AdapterContractError("IDEMPOTENCY_CONFLICT", "Esta solicitação já possui uma sessão associada; reutilize a operação idempotente original.")

        now = datetime.now(timezone.utc)
        valid_from = _as_utc(command.valid_from)
        expires_at = _as_utc(command.expires_at)
        mfa_at = _as_utc(command.mfa_verified_at)
        if now < valid_from:
            raise AdapterContractError("INVALID_WINDOW", "A janela ainda não começou; provisionar somente no horário autorizado.", True)
        if now >= expires_at:
            raise AdapterContractError("INVALID_WINDOW", "A janela solicitada já expirou.")
        if now - mfa_at > self._mfa_freshness or mfa_at > now:
            raise AdapterContractError("MFA_REQUIRED", "MFA ausente, futura ou fora da janela de frescor.", True)
        approvals_needed = 2 if command.requires_dual_approval else 1
        if len(set(command.approval_ids)) < approvals_needed:
            raise AdapterContractError("INSUFFICIENT_APPROVALS", f"São necessárias {approvals_needed} aprovações distintas.")
        if expires_at - valid_from > self._max_session_duration:
            raise AdapterContractError("INVALID_WINDOW", "A duração excede o limite configurado.")

        self._counter += 1
        session_id = f"SIM-SESSION-{self._counter:06d}"
        result = SessionResult(
            status=SessionStatus.ACTIVE,
            provider="SIMULATED",
            external_session_id=session_id,
            request_id=command.request_id,
            asset_id=command.asset_id,
            user_id=command.user_id,
            work_order_id=command.work_order_id,
            access_profile=command.access_profile,
            started_at=now,
            expires_at=expires_at,
            correlation_id=command.correlation_id,
        )
        self._sessions[session_id] = result
        self._request_sessions[command.request_id] = session_id
        self._idempotency[command.idempotency_key] = (fp, session_id)
        return replace(result)

    def restore_session(self, session: SessionResult) -> None:
        """Restore a session persisted by the backend database after a process restart.

        The simulator remains hardware/network-free; this only rebuilds its local
        in-memory view from a previously saved simulated session.
        """
        self._sessions[session.external_session_id] = replace(session)
        self._request_sessions[session.request_id] = session.external_session_id
        # Keep generated demo identifiers unique after a restart.
        prefix = "SIM-SESSION-"
        if session.external_session_id.startswith(prefix):
            suffix = session.external_session_id[len(prefix):]
            if suffix.isdigit():
                self._counter = max(self._counter, int(suffix))

    def get_session(self, session_id: str) -> SessionResult:
        if session_id not in self._sessions:
            raise AdapterContractError("SESSION_NOT_FOUND", "Sessão não encontrada.")
        session = self._sessions[session_id]
        self._expire_if_needed(session)
        return replace(session)

    def revoke_session(self, session_id: str, reason: str, idempotency_key: str) -> SessionResult:
        if not idempotency_key.strip():
            raise AdapterContractError("IDEMPOTENCY_CONFLICT", "Chave idempotente de revogação obrigatória.")
        if idempotency_key in self._revoke_keys:
            if self._revoke_keys[idempotency_key] != session_id:
                raise AdapterContractError("IDEMPOTENCY_CONFLICT", "Chave de revogação reutilizada para outra sessão.")
            return self.get_session(session_id)
        if session_id not in self._sessions:
            raise AdapterContractError("SESSION_NOT_FOUND", "Sessão não encontrada.")

        # IMPORTANT: mutate the canonical object in self._sessions. get_session()
        # returns a defensive copy, so mutating its result would not persist REVOKED.
        session = self._sessions[session_id]
        self._expire_if_needed(session)
        self._revoke_keys[idempotency_key] = session_id
        if session.status in {SessionStatus.REVOKED, SessionStatus.EXPIRED, SessionStatus.CLOSED, SessionStatus.FAILED}:
            return replace(session)
        session.status = SessionStatus.REVOKED
        session.closed_at = datetime.now(timezone.utc)
        session.status_reason = reason.strip() or "Revogada pela ValidaOT."
        return replace(session)

    def _validate_command(self, command: GrantSessionCommand) -> None:
        required = {
            "request_id": command.request_id,
            "idempotency_key": command.idempotency_key,
            "asset_id": command.asset_id,
            "gateway_ref": command.gateway_ref,
            "user_id": command.user_id,
            "external_identity_ref": command.external_identity_ref,
            "work_order_id": command.work_order_id,
            "work_order_code": command.work_order_code,
            "correlation_id": command.correlation_id,
        }
        if any(not str(value).strip() for value in required.values()):
            raise AdapterContractError("INVALID_COMMAND", "Campos obrigatórios não podem estar vazios.")
        _ensure_aware(command.valid_from, "valid_from")
        _ensure_aware(command.expires_at, "expires_at")
        _ensure_aware(command.mfa_verified_at, "mfa_verified_at")
        if _as_utc(command.expires_at) <= _as_utc(command.valid_from):
            raise AdapterContractError("INVALID_WINDOW", "expires_at deve ser posterior a valid_from.")
        if command.requires_dual_approval and len(set(command.approval_ids)) < 2:
            raise AdapterContractError("INSUFFICIENT_APPROVALS", "Acesso crítico exige duas aprovações distintas.")
        if not command.requires_dual_approval and len(set(command.approval_ids)) < 1:
            raise AdapterContractError("INSUFFICIENT_APPROVALS", "Acesso exige ao menos uma aprovação.")

    @staticmethod
    def _expire_if_needed(session: SessionResult) -> None:
        if session.status == SessionStatus.ACTIVE and datetime.now(timezone.utc) >= session.expires_at:
            session.status = SessionStatus.EXPIRED
            session.closed_at = datetime.now(timezone.utc)
            session.status_reason = "A janela autorizada terminou."
