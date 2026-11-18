"""ValidaOT academic backend starter.

TOTP is verified by the backend. Industrial sessions are simulated in memory and
no network/hardware connection is made to SCADA, HMI, engineering stations or PLCs.
Audit events are exposed through a read-only endpoint for OT_ADMIN and AUDITOR.
Use only for local development/demo until security review and deployment hardening.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import io
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Generator, Optional

import jwt
import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import (Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer,
                        String, Text, UniqueConstraint, create_engine, func, select, text, update)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from validaot_adapter_contract import (
    AccessProfile as AdapterAccessProfile,
    AdapterContractError,
    GrantSessionCommand,
    SessionResult as AdapterSessionResult,
    SessionStatus as AdapterSessionStatus,
    SimulatedAccessAdapter,
)
from audit_integrity_common import compute_event_hash

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "ValidaOT API")
APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./validaot.db")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")
TOTP_ISSUER = os.getenv("TOTP_ISSUER", "ValidaOT")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
MFA_CHALLENGE_MINUTES = int(os.getenv("MFA_CHALLENGE_MINUTES", "10"))
MFA_FRESHNESS_SECONDS = int(os.getenv("MFA_FRESHNESS_SECONDS", "600"))
MFA_SETUP_TTL_MINUTES = int(os.getenv("MFA_SETUP_TTL_MINUTES", "10"))
MFA_MAX_FAILED_ATTEMPTS = int(os.getenv("MFA_MAX_FAILED_ATTEMPTS", "5"))
MFA_LOCKOUT_MINUTES = int(os.getenv("MFA_LOCKOUT_MINUTES", "10"))
MAX_SESSION_MINUTES = int(os.getenv("MAX_SESSION_MINUTES", "120"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hasher = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    TECHNICIAN = "TECHNICIAN"
    APPROVER = "APPROVER"
    OT_ADMIN = "OT_ADMIN"
    AUDITOR = "AUDITOR"


class CompanyType(str, Enum):
    INDUSTRY = "INDUSTRY"
    CONTRACTOR = "CONTRACTOR"


class RecordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISABLED = "DISABLED"


class AssetType(str, Enum):
    ENGINEERING_STATION = "ENGINEERING_STATION"
    SCADA_SERVER = "SCADA_SERVER"
    HMI = "HMI"
    PLC = "PLC"


class Criticality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WorkOrderStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AccessProfile(str, Enum):
    READ_ONLY = "READ_ONLY"
    DIAGNOSTIC = "DIAGNOSTIC"
    MAINTENANCE = "MAINTENANCE"


class RequestStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Decision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SessionState(str, Enum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    REVOKING = "REVOKING"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[Optional[str]] = mapped_column(ForeignKey("companies.id"), nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow())


class MfaCredential(Base):
    __tablename__ = "user_mfa_credentials"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accepted_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow(), onupdate=lambda: utcnow())


class IndustrialSite(Base):
    __tablename__ = "industrial_sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Recife")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    __table_args__ = (UniqueConstraint("owner_company_id", "code", name="uq_site_company_code"),)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[str] = mapped_column(ForeignKey("industrial_sites.id"), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    gateway_ref: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    __table_args__ = (UniqueConstraint("site_id", "asset_code", name="uq_asset_site_code"),)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("industrial_sites.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    assigned_technician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    responsible_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    planned_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    description: Mapped[str] = mapped_column(Text, nullable=False)


class AccessRequest(Base):
    __tablename__ = "access_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    access_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    requested_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mfa_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_APPROVAL")
    requires_dual_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criticality_reason: Mapped[str] = mapped_column(String(30), nullable=False, default="NONE")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow())
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    access_request_id: Mapped[str] = mapped_column(ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow())
    __table_args__ = (UniqueConstraint("access_request_id", "approver_id", name="uq_approval_per_user"),)


class AccessSession(Base):
    __tablename__ = "access_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    access_request_id: Mapped[str] = mapped_column(ForeignKey("access_requests.id"), unique=True, nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(40), nullable=False, default="SIMULATED")
    external_session_id: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow())
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Nullable for the 64 historical events anchored by the external baseline.
    # Events created after migration receive sequence + hash fields.
    chain_sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True)
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class AuditChainState(Base):
    __tablename__ = "audit_chain_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    anchor_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_config() -> None:
    if len(JWT_SECRET_KEY) < 32 or JWT_SECRET_KEY.startswith("replace_"):
        raise RuntimeError("Configure JWT_SECRET_KEY com um segredo aleatório de pelo menos 32 caracteres no arquivo .env.")
    try:
        Fernet(MFA_ENCRYPTION_KEY.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("Configure MFA_ENCRYPTION_KEY com uma chave Fernet válida no arquivo .env.") from exc


def fernet() -> Fernet:
    try:
        return Fernet(MFA_ENCRYPTION_KEY.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Configuração de criptografia MFA inválida.") from exc


def encrypt_secret(secret: str) -> str:
    return fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted: str) -> str:
    try:
        return fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Não foi possível desbloquear a credencial MFA.") from exc


def create_token(user: User, token_type: str, minutes: int, mfa_verified_at: Optional[datetime] = None) -> str:
    now = utcnow()
    payload = {
        "sub": user.id,
        "role": user.role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": str(uuid.uuid4()),
    }
    if mfa_verified_at is not None:
        payload["mfa_verified_at"] = ensure_utc(mfa_verified_at).isoformat()
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expirado. Entre novamente.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Token inválido.") from exc


def get_auth_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Token Bearer obrigatório.")
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token de desafio não pode acessar este recurso.")
    user = db.get(User, payload.get("sub"))
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="Usuário inexistente ou inativo.")
    return user, payload


def get_challenge_context(
    expected_type: str,
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
) -> tuple[User, dict]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Token Bearer de desafio obrigatório.")
    payload = decode_token(credentials.credentials)
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Token de desafio inválido para esta operação.")
    user = db.get(User, payload.get("sub"))
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="Usuário inexistente ou inativo.")
    if user.role != Role.TECHNICIAN.value:
        raise HTTPException(status_code=403, detail="Este fluxo de MFA é obrigatório para técnicos terceirizados.")
    return user, payload


def log_event(db: Session, actor_id: Optional[str], event_type: str, entity_type: str,
              entity_id: str, outcome: str, details: dict | None = None,
              correlation_id: Optional[str] = None) -> str:
    """Append an audit event to the hash chain in the same DB transaction.

    The migration must have initialized audit_chain_state from the verified
    external baseline before this version of the API is started.
    """
    corr = correlation_id or str(uuid.uuid4())
    state = db.get(AuditChainState, 1)
    if state is None:
        raise RuntimeError(
            "Cadeia de auditoria nao inicializada. Execute migrate_audit_integrity_v0_6.py "
            "antes de iniciar esta versao do backend."
        )

    sequence = int(state.last_sequence) + 1
    previous_hash = state.last_hash
    event_id = str(uuid.uuid4())
    event = AuditEvent(
        id=event_id,
        actor_user_id=actor_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_at=utcnow(),
        correlation_id=corr,
        outcome=outcome,
        details=json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
        chain_sequence=sequence,
        previous_hash=previous_hash,
        event_hash=None,
    )
    db.add(event)
    # Flush to read back SQLite's exact stored timestamp representation before hashing.
    db.flush()
    stored = db.execute(
        text("""SELECT id, actor_user_id, event_type, entity_type, entity_id, occurred_at,
                     correlation_id, outcome, details
              FROM audit_events WHERE id = :event_id"""),
        {"event_id": event_id},
    ).mappings().one()
    digest = compute_event_hash(sequence, previous_hash, stored)
    event.event_hash = digest
    state.last_sequence = sequence
    state.last_hash = digest
    state.updated_at = utcnow()
    return corr


def qr_png_data_uri(uri: str) -> str:
    image = qrcode.make(uri)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _check_lockout(credential: MfaCredential) -> None:
    locked_until = ensure_utc(credential.locked_until)
    if locked_until and utcnow() < locked_until:
        raise HTTPException(status_code=429, detail="Muitas tentativas MFA. Aguarde o bloqueio temporário.")


def _record_failed_attempt(db: Session, credential: MfaCredential) -> None:
    credential.failed_attempts += 1
    if credential.failed_attempts >= MFA_MAX_FAILED_ATTEMPTS:
        credential.locked_until = utcnow() + timedelta(minutes=MFA_LOCKOUT_MINUTES)
        credential.failed_attempts = 0
    # Record failed MFA attempts without logging the supplied code or secret.
    log_event(db, credential.user_id, "MFA_VERIFICATION_FAILED", "USER",
              credential.user_id, "DENIED", {"reason": "INVALID_EXPIRED_OR_REUSED_CODE"})
    db.commit()


def _match_totp_counter(secret: str, code: str, last_counter: int) -> Optional[int]:
    if not re.fullmatch(r"\d{6}", code or ""):
        return None
    totp = pyotp.TOTP(secret, digits=6, interval=30)
    current = int(time.time()) // totp.interval
    matches: list[int] = []
    for counter in (current, current - 1, current + 1):
        if counter > last_counter and hmac.compare_digest(totp.generate_otp(counter), code):
            matches.append(counter)
    return max(matches) if matches else None


def consume_totp(db: Session, credential: MfaCredential, code: str) -> datetime:
    """Validate and atomically consume a fresh time-step to prevent code replay."""
    _check_lockout(credential)
    secret = decrypt_secret(credential.secret_encrypted)
    counter = _match_totp_counter(secret, code, credential.last_accepted_counter)
    if counter is None:
        _record_failed_attempt(db, credential)
        raise HTTPException(status_code=401, detail="Código MFA inválido, expirado ou já utilizado.")
    # Conditional update prevents accepting the same time-step in concurrent requests.
    result = db.execute(
        update(MfaCredential)
        .where(MfaCredential.user_id == credential.user_id,
               MfaCredential.last_accepted_counter < counter)
        .values(last_accepted_counter=counter, last_verified_at=utcnow(), failed_attempts=0, locked_until=None)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=401, detail="Código MFA já utilizado; informe um novo código.")
    verified_at = utcnow()
    db.commit()
    return verified_at


def _mfa_credential(db: Session, user_id: str) -> Optional[MfaCredential]:
    return db.get(MfaCredential, user_id)


def require_role(user: User, *roles: Role) -> None:
    if user.role not in {r.value for r in roles}:
        raise HTTPException(status_code=403, detail="Seu perfil não permite esta operação.")


def response_user(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "email": user.email,
            "role": user.role, "mfa_enabled": user.mfa_enabled, "status": user.status}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class AccessRequestCreate(BaseModel):
    work_order_id: str
    asset_id: str
    access_profile: AccessProfile
    rationale: str = Field(min_length=5, max_length=1500)
    requested_start_at: datetime
    requested_end_at: datetime


class ApprovalCreate(BaseModel):
    decision: Decision
    note: Optional[str] = Field(default=None, max_length=1500)


app = FastAPI(title=APP_NAME, version="0.7.0", description=(
    "Backend acadêmico ValidaOT. O adaptador de acesso é simulado; nenhuma comunicação industrial real é realizada."
))


@app.on_event("startup")
def startup() -> None:
    _validate_config()
    Base.metadata.create_all(bind=engine)
    # Never silently start a chain-enabled API without an initialized state row.
    chain_db = SessionLocal()
    try:
        if chain_db.get(AuditChainState, 1) is None:
            raise RuntimeError(
                "Cadeia de auditoria nao inicializada. Execute migrate_audit_integrity_v0_6.py "
                "com o baseline externo antes de iniciar a API."
            )
    finally:
        chain_db.close()
    # The adapter simulator stores live state in memory. Rehydrate sessions from
    # the application's database after --reload or process restart so saved demo
    # sessions remain queryable/revocable in the MVP. This does not connect to OT.
    db = SessionLocal()
    try:
        saved_sessions = db.scalars(
            select(AccessSession).where(
                AccessSession.adapter_name == "SIMULATED",
                AccessSession.external_session_id.is_not(None),
            )
        ).all()
        for record in saved_sessions:
            request = db.get(AccessRequest, record.access_request_id)
            if request is None:
                continue
            try:
                session_status = AdapterSessionStatus(record.status)
                access_profile = AdapterAccessProfile(request.access_profile)
            except ValueError:
                continue
            adapter.restore_session(
                AdapterSessionResult(
                    status=session_status,
                    provider=record.adapter_name,
                    external_session_id=record.external_session_id,
                    request_id=request.id,
                    asset_id=request.asset_id,
                    user_id=request.requester_id,
                    work_order_id=request.work_order_id,
                    access_profile=access_profile,
                    started_at=ensure_utc(record.started_at or record.valid_from),
                    expires_at=ensure_utc(record.expires_at),
                    correlation_id=record.correlation_id,
                    closed_at=ensure_utc(record.closed_at),
                    status_reason=record.status_reason,
                )
            )
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": APP_NAME, "adapter": "SIMULATED", "industrial_network_connected": False}


@app.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user is None or user.status != "ACTIVE" or not password_hasher.verify(body.password, user.password_hash):
        # Uniform response to avoid exposing whether an account exists.
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    if user.role == Role.TECHNICIAN.value:
        credential = _mfa_credential(db, user.id)
        if not user.mfa_enabled or credential is None or not credential.enabled:
            challenge = create_token(user, "mfa_setup", MFA_CHALLENGE_MINUTES)
            return {"status": "MFA_SETUP_REQUIRED", "challenge_token": challenge,
                    "expires_in_seconds": MFA_CHALLENGE_MINUTES * 60}
        challenge = create_token(user, "mfa_verify", MFA_CHALLENGE_MINUTES)
        return {"status": "MFA_REQUIRED", "challenge_token": challenge,
                "expires_in_seconds": MFA_CHALLENGE_MINUTES * 60}
    token = create_token(user, "access", ACCESS_TOKEN_MINUTES)
    log_event(db, user.id, "LOGIN_SUCCESS", "USER", user.id, "SUCCESS")
    db.commit()
    return {"status": "AUTHENTICATED", "access_token": token, "token_type": "bearer",
            "expires_in_seconds": ACCESS_TOKEN_MINUTES * 60, "user": response_user(user)}


@app.post("/auth/mfa/setup")
def mfa_setup(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = get_challenge_context("mfa_setup", credentials, db)
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA já está habilitado nesta conta.")
    secret = pyotp.random_base32()
    credential = db.get(MfaCredential, user.id)
    expiry = utcnow() + timedelta(minutes=MFA_SETUP_TTL_MINUTES)
    if credential is None:
        credential = MfaCredential(user_id=user.id, secret_encrypted=encrypt_secret(secret),
                                   enabled=False, pending_expires_at=expiry, last_accepted_counter=-1)
        db.add(credential)
    else:
        credential.secret_encrypted = encrypt_secret(secret)
        credential.enabled = False
        credential.pending_expires_at = expiry
        credential.last_accepted_counter = -1
        credential.last_verified_at = None
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=TOTP_ISSUER)
    log_event(db, user.id, "MFA_SETUP_STARTED", "USER", user.id, "SUCCESS")
    db.commit()
    return {"status": "MFA_SETUP_PENDING", "issuer": TOTP_ISSUER, "account": user.email,
            "provisioning_uri": uri, "qr_code_data_uri": qr_png_data_uri(uri),
            "expires_at": expiry.isoformat(),
            "message": "Escaneie o QR Code em seu autenticador e confirme com o código atual. Não compartilhe este QR Code."}


@app.post("/auth/mfa/confirm")
def mfa_confirm(
    body: CodeRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = get_challenge_context("mfa_setup", credentials, db)
    credential = _mfa_credential(db, user.id)
    if credential is None or credential.enabled:
        raise HTTPException(status_code=409, detail="Não existe configuração MFA pendente.")
    if not ensure_utc(credential.pending_expires_at) or utcnow() >= ensure_utc(credential.pending_expires_at):
        raise HTTPException(status_code=410, detail="Configuração MFA expirada. Inicie novamente.")
    verified_at = consume_totp(db, credential, body.code)
    credential = db.get(MfaCredential, user.id)
    credential.enabled = True
    credential.pending_expires_at = None
    user.mfa_enabled = True
    log_event(db, user.id, "MFA_ENABLED", "USER", user.id, "SUCCESS")
    db.commit()
    access_token = create_token(user, "access", ACCESS_TOKEN_MINUTES, verified_at)
    return {"status": "MFA_ENABLED", "access_token": access_token, "token_type": "bearer",
            "expires_in_seconds": ACCESS_TOKEN_MINUTES * 60, "mfa_verified_at": verified_at.isoformat(),
            "user": response_user(user)}


@app.post("/auth/mfa/verify")
def mfa_verify(
    body: CodeRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = get_challenge_context("mfa_verify", credentials, db)
    credential = _mfa_credential(db, user.id)
    if credential is None or not credential.enabled or not user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA não está habilitado para esta conta.")
    verified_at = consume_totp(db, credential, body.code)
    log_event(db, user.id, "MFA_VERIFIED", "USER", user.id, "SUCCESS")
    db.commit()
    return {"status": "AUTHENTICATED", "access_token": create_token(user, "access", ACCESS_TOKEN_MINUTES, verified_at),
            "token_type": "bearer", "expires_in_seconds": ACCESS_TOKEN_MINUTES * 60,
            "mfa_verified_at": verified_at.isoformat(), "user": response_user(user)}


@app.post("/auth/mfa/refresh")
def mfa_refresh(
    body: CodeRequest,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = ctx
    require_role(user, Role.TECHNICIAN)
    credential = _mfa_credential(db, user.id)
    if credential is None or not credential.enabled:
        raise HTTPException(status_code=403, detail="Configure o MFA antes de continuar.")
    verified_at = consume_totp(db, credential, body.code)
    log_event(db, user.id, "MFA_REFRESHED", "USER", user.id, "SUCCESS")
    db.commit()
    return {"status": "MFA_REFRESHED", "access_token": create_token(user, "access", ACCESS_TOKEN_MINUTES, verified_at),
            "token_type": "bearer", "expires_in_seconds": ACCESS_TOKEN_MINUTES * 60,
            "mfa_verified_at": verified_at.isoformat()}


@app.get("/auth/me")
def me(ctx: tuple[User, dict] = Depends(get_auth_context)) -> dict:
    user, payload = ctx
    mfa_verified_at = payload.get("mfa_verified_at")
    return {"user": response_user(user), "mfa_verified_at": mfa_verified_at}


@app.get("/assets")
def list_assets(
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    user, _ = ctx
    require_role(user, Role.TECHNICIAN, Role.APPROVER, Role.OT_ADMIN, Role.AUDITOR)
    rows = list(db.scalars(select(Asset).order_by(Asset.asset_code)))
    return [{"id": a.id, "asset_code": a.asset_code, "name": a.name, "asset_type": a.asset_type,
             "criticality": a.criticality, "gateway_ref": a.gateway_ref, "site_id": a.site_id, "status": a.status}
            for a in rows]


@app.get("/work-orders")
def list_work_orders(
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    user, _ = ctx
    query = select(WorkOrder).order_by(WorkOrder.code)
    if user.role == Role.TECHNICIAN.value:
        query = query.where(WorkOrder.assigned_technician_id == user.id)
    rows = list(db.scalars(query))
    return [{"id": w.id, "code": w.code, "site_id": w.site_id, "asset_id": w.asset_id,
             "assigned_technician_id": w.assigned_technician_id, "responsible_user_id": w.responsible_user_id,
             "planned_start_at": ensure_utc(w.planned_start_at).isoformat(),
             "planned_end_at": ensure_utc(w.planned_end_at).isoformat(),
             "is_critical": w.is_critical, "status": w.status, "description": w.description}
            for w in rows]


def _serialize_access_requests(db: Session, requests: list[AccessRequest]) -> list[dict]:
    """Build enriched, read-only request records with approval and related-entity details."""
    if not requests:
        return []

    request_ids = [item.id for item in requests]
    requester_ids = {item.requester_id for item in requests}
    work_order_ids = {item.work_order_id for item in requests}
    asset_ids = {item.asset_id for item in requests}

    approvals = list(db.scalars(
        select(Approval)
        .where(Approval.access_request_id.in_(request_ids))
        .order_by(Approval.decided_at.asc(), Approval.id.asc())
    ))
    approver_ids = {item.approver_id for item in approvals}
    all_user_ids = requester_ids | approver_ids

    users = list(db.scalars(select(User).where(User.id.in_(all_user_ids)))) if all_user_ids else []
    users_by_id = {item.id: item for item in users}
    orders = list(db.scalars(select(WorkOrder).where(WorkOrder.id.in_(work_order_ids)))) if work_order_ids else []
    orders_by_id = {item.id: item for item in orders}
    assets = list(db.scalars(select(Asset).where(Asset.id.in_(asset_ids)))) if asset_ids else []
    assets_by_id = {item.id: item for item in assets}

    approvals_by_request: dict[str, list[Approval]] = {}
    for approval in approvals:
        approvals_by_request.setdefault(approval.access_request_id, []).append(approval)

    result: list[dict] = []
    for request in requests:
        requester = users_by_id.get(request.requester_id)
        order = orders_by_id.get(request.work_order_id)
        asset = assets_by_id.get(request.asset_id)
        request_approvals = approvals_by_request.get(request.id, [])
        approved_count = sum(1 for item in request_approvals if item.decision == Decision.APPROVED.value)
        rejected_count = sum(1 for item in request_approvals if item.decision == Decision.REJECTED.value)
        required_approvals = 2 if request.requires_dual_approval else 1
        remaining_approvals = (
            max(required_approvals - approved_count, 0)
            if request.status == RequestStatus.PENDING_APPROVAL.value else 0
        )

        approval_details = []
        for approval in request_approvals:
            approver = users_by_id.get(approval.approver_id)
            approval_details.append({
                "id": approval.id,
                "approver_id": approval.approver_id,
                "approver_name": approver.full_name if approver else None,
                "approver_email": approver.email if approver else None,
                "decision": approval.decision,
                "note": approval.note,
                "decided_at": ensure_utc(approval.decided_at).isoformat(),
            })

        result.append({
            "id": request.id,
            "request_code": request.request_code,
            "requester_id": request.requester_id,
            "requester_name": requester.full_name if requester else None,
            "requester_email": requester.email if requester else None,
            "work_order_id": request.work_order_id,
            "work_order_code": order.code if order else None,
            "work_order_status": order.status if order else None,
            "work_order_is_critical": order.is_critical if order else None,
            "asset_id": request.asset_id,
            "asset_code": asset.asset_code if asset else None,
            "asset_name": asset.name if asset else None,
            "asset_type": asset.asset_type if asset else None,
            "asset_criticality": asset.criticality if asset else None,
            "access_profile": request.access_profile,
            "requested_start_at": ensure_utc(request.requested_start_at).isoformat(),
            "requested_end_at": ensure_utc(request.requested_end_at).isoformat(),
            "status": request.status,
            "requires_dual_approval": request.requires_dual_approval,
            "criticality_reason": request.criticality_reason,
            "rationale": request.rationale,
            "submitted_at": ensure_utc(request.submitted_at).isoformat(),
            "decision_reason": request.decision_reason,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "required_approvals": required_approvals,
            "remaining_approvals": remaining_approvals,
            "approvals": approval_details,
        })
    return result


@app.get("/access-requests")
def list_access_requests(
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[dict]:
    user, _ = ctx
    require_role(user, Role.TECHNICIAN, Role.APPROVER, Role.OT_ADMIN, Role.AUDITOR)
    query = select(AccessRequest).order_by(AccessRequest.submitted_at.desc(), AccessRequest.id.desc())
    if user.role == Role.TECHNICIAN.value:
        query = query.where(AccessRequest.requester_id == user.id)
    elif user.role == Role.APPROVER.value:
        query = query.where(AccessRequest.status == RequestStatus.PENDING_APPROVAL.value)
    rows = list(db.scalars(query))
    return _serialize_access_requests(db, rows)


@app.get("/access-requests/{request_id}")
def get_access_request_details(
    request_id: str,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """Return one request with its approvers and quorum summary, subject to role scope."""
    user, _ = ctx
    require_role(user, Role.TECHNICIAN, Role.APPROVER, Role.OT_ADMIN, Role.AUDITOR)
    request = db.get(AccessRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if user.role == Role.TECHNICIAN.value and request.requester_id != user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta solicitação.")
    if user.role == Role.APPROVER.value and request.status != RequestStatus.PENDING_APPROVAL.value:
        raise HTTPException(status_code=403, detail="A solicitação não está disponível para este aprovador.")
    return _serialize_access_requests(db, [request])[0]


@app.post("/access-requests", status_code=201)
def create_access_request(
    body: AccessRequestCreate,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = ctx
    require_role(user, Role.TECHNICIAN)
    order = db.get(WorkOrder, body.work_order_id)
    asset = db.get(Asset, body.asset_id)
    if order is None or asset is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço ou ativo não encontrado.")
    if order.assigned_technician_id != user.id:
        raise HTTPException(status_code=403, detail="Você não está atribuído a esta ordem de serviço.")
    if order.status not in {WorkOrderStatus.OPEN.value, WorkOrderStatus.IN_PROGRESS.value}:
        raise HTTPException(status_code=409, detail="A ordem de serviço não está aberta para solicitações.")
    if order.asset_id != asset.id or order.site_id != asset.site_id:
        raise HTTPException(status_code=422, detail="O ativo deve corresponder ao ativo principal da ordem de serviço.")
    start = ensure_utc(body.requested_start_at)
    end = ensure_utc(body.requested_end_at)
    if start is None or end is None or end <= start:
        raise HTTPException(status_code=422, detail="A janela solicitada é inválida.")
    if start < ensure_utc(order.planned_start_at) or end > ensure_utc(order.planned_end_at):
        raise HTTPException(status_code=422, detail="A janela solicitada deve estar dentro da janela da ordem de serviço.")
    if end - start > timedelta(minutes=MAX_SESSION_MINUTES):
        raise HTTPException(status_code=422, detail=f"A sessão não pode exceder {MAX_SESSION_MINUTES} minutos.")
    critical_asset = asset.criticality == Criticality.CRITICAL.value
    critical_order = order.is_critical
    dual = critical_asset or critical_order
    reason = "BOTH" if critical_asset and critical_order else "ASSET_CRITICAL" if critical_asset else "WORK_ORDER_CRITICAL" if critical_order else "NONE"
    request = AccessRequest(
        request_code=f"REQ-{uuid.uuid4().hex[:10].upper()}", requester_id=user.id,
        work_order_id=order.id, asset_id=asset.id, access_profile=body.access_profile.value,
        rationale=body.rationale, requested_start_at=start, requested_end_at=end,
        status=RequestStatus.PENDING_APPROVAL.value, requires_dual_approval=dual,
        criticality_reason=reason, submitted_at=utcnow(),
    )
    db.add(request)
    db.flush()
    log_event(db, user.id, "ACCESS_REQUEST_SUBMITTED", "ACCESS_REQUEST", request.id, "SUCCESS",
              {"requires_dual_approval": dual, "criticality_reason": reason})
    db.commit()
    return {"id": request.id, "request_code": request.request_code, "status": request.status,
            "requires_dual_approval": request.requires_dual_approval, "criticality_reason": request.criticality_reason,
            "required_approvals": 2 if dual else 1}


@app.post("/access-requests/{request_id}/decision")
def decide_access_request(
    request_id: str,
    body: ApprovalCreate,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    approver, _ = ctx
    require_role(approver, Role.APPROVER)
    request = db.get(AccessRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if request.status != RequestStatus.PENDING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="A solicitação não está aguardando aprovação.")
    if approver.id == request.requester_id:
        raise HTTPException(status_code=403, detail="O solicitante não pode aprovar sua própria solicitação.")
    existing = db.scalar(select(Approval).where(Approval.access_request_id == request.id,
                                                Approval.approver_id == approver.id))
    if existing:
        raise HTTPException(status_code=409, detail="Você já tomou uma decisão para esta solicitação.")
    approval = Approval(access_request_id=request.id, approver_id=approver.id,
                        decision=body.decision.value, note=body.note, decided_at=utcnow())
    db.add(approval)
    if body.decision == Decision.REJECTED:
        request.status = RequestStatus.REJECTED.value
        request.decision_reason = body.note or "Solicitação rejeitada pelo aprovador."
    else:
        db.flush()
        # Count with an aggregate to decide whether the required quorum has been reached.
        from sqlalchemy import func
        approved_count = db.scalar(select(func.count()).select_from(Approval).where(
            Approval.access_request_id == request.id, Approval.decision == Decision.APPROVED.value)) or 0
        needed = 2 if request.requires_dual_approval else 1
        if approved_count >= needed:
            request.status = RequestStatus.APPROVED.value
    log_event(db, approver.id, "ACCESS_REQUEST_DECISION", "ACCESS_REQUEST", request.id,
              "SUCCESS", {"decision": body.decision.value, "request_status": request.status})
    db.commit()
    from sqlalchemy import func
    approved_count = db.scalar(select(func.count()).select_from(Approval).where(
        Approval.access_request_id == request.id, Approval.decision == Decision.APPROVED.value)) or 0
    return {"request_id": request.id, "request_status": request.status,
            "approved_count": approved_count, "required_approvals": 2 if request.requires_dual_approval else 1}


@app.post("/access-requests/{request_id}/authorize")
def authorize_access_request(
    request_id: str,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    technician, token_payload = ctx
    require_role(technician, Role.TECHNICIAN)
    request = db.get(AccessRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if request.requester_id != technician.id:
        raise HTTPException(status_code=403, detail="Somente o técnico solicitante pode iniciar esta sessão.")
    if request.status != RequestStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="A solicitação ainda não tem todas as aprovações exigidas.")
    mfa_at_raw = token_payload.get("mfa_verified_at")
    if not mfa_at_raw:
        raise HTTPException(status_code=403, detail="MFA recente é obrigatório antes de liberar a sessão.")
    mfa_at = ensure_utc(datetime.fromisoformat(mfa_at_raw))
    now = utcnow()
    if mfa_at is None or mfa_at > now or now - mfa_at > timedelta(seconds=MFA_FRESHNESS_SECONDS):
        raise HTTPException(status_code=403, detail="MFA expirado. Use /auth/mfa/refresh e tente novamente.")
    order = db.get(WorkOrder, request.work_order_id)
    asset = db.get(Asset, request.asset_id)
    if order is None or asset is None or order.status not in {WorkOrderStatus.OPEN.value, WorkOrderStatus.IN_PROGRESS.value}:
        raise HTTPException(status_code=409, detail="A ordem de serviço ou o ativo deixou de estar disponível.")
    approvals = list(db.scalars(select(Approval).where(Approval.access_request_id == request.id,
                                                  Approval.decision == Decision.APPROVED.value)))
    distinct_approvers = {a.approver_id for a in approvals}
    required = 2 if request.requires_dual_approval else 1
    if len(distinct_approvers) < required:
        raise HTTPException(status_code=403, detail="Quantidade de aprovações insuficiente.")
    if now < ensure_utc(request.requested_start_at) or now >= ensure_utc(request.requested_end_at):
        raise HTTPException(status_code=409, detail="A janela autorizada ainda não começou ou já terminou.")
    existing_session = db.scalar(select(AccessSession).where(AccessSession.access_request_id == request.id))
    if existing_session:
        return {"request_id": request.id, "session_id": existing_session.external_session_id,
                "status": existing_session.status, "message": "Sessão já registrada; não foi criada duplicata."}
    correlation_id = str(uuid.uuid4())
    idempotency_key = f"grant:{request.id}"
    command = GrantSessionCommand(
        request_id=request.id, idempotency_key=idempotency_key, asset_id=asset.id,
        gateway_ref=asset.gateway_ref, user_id=technician.id,
        external_identity_ref=f"SIM-USER-{technician.id}", work_order_id=order.id,
        work_order_code=order.code, access_profile=AdapterAccessProfile(request.access_profile),
        valid_from=ensure_utc(request.requested_start_at), expires_at=ensure_utc(request.requested_end_at),
        mfa_verified_at=mfa_at, requires_dual_approval=request.requires_dual_approval,
        approval_ids=tuple(sorted(a.id for a in approvals)), correlation_id=correlation_id,
    )
    try:
        result = adapter.grant_session(command)
    except AdapterContractError as exc:
        log_event(db, technician.id, "SESSION_GRANT_FAILED", "ACCESS_REQUEST", request.id,
                  "DENIED", {"error_code": exc.error.code}, correlation_id)
        db.commit()
        raise HTTPException(status_code=409, detail={"code": exc.error.code, "message": exc.error.message,
                                                     "retryable": exc.error.retryable}) from exc
    session_record = AccessSession(
        # Assign the primary key before creating the audit event. SQLAlchemy's
        # column default is normally evaluated during INSERT/flush, but the
        # audit event needs this ID before the transaction is committed.
        id=str(uuid.uuid4()),
        access_request_id=request.id, adapter_name=result.provider,
        external_session_id=result.external_session_id, idempotency_key=idempotency_key,
        status=result.status.value, valid_from=ensure_utc(result.started_at),
        expires_at=ensure_utc(result.expires_at), started_at=ensure_utc(result.started_at),
        correlation_id=correlation_id,
    )
    request.mfa_verified_at = mfa_at
    db.add(session_record)
    log_event(db, technician.id, "SESSION_GRANTED_SIMULATED", "ACCESS_SESSION", session_record.id,
              "SUCCESS", {"adapter": result.provider, "profile": request.access_profile}, correlation_id)
    db.commit()
    return {"request_id": request.id, "session_id": result.external_session_id,
            "status": result.status.value, "adapter": result.provider,
            "started_at": result.started_at.isoformat(), "expires_at": result.expires_at.isoformat(),
            "industrial_network_connected": False}


@app.get("/audit-events")
def list_audit_events(
    event_type: Optional[str] = Query(default=None, min_length=1, max_length=80),
    entity_type: Optional[str] = Query(default=None, min_length=1, max_length=60),
    entity_id: Optional[str] = Query(default=None, min_length=1, max_length=36),
    outcome: Optional[str] = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only, paginated audit view for OT administrators and auditors."""
    user, _ = ctx
    require_role(user, Role.OT_ADMIN, Role.AUDITOR)

    filters = []
    if event_type is not None:
        filters.append(AuditEvent.event_type == event_type)
    if entity_type is not None:
        filters.append(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditEvent.entity_id == entity_id)
    if outcome is not None:
        filters.append(AuditEvent.outcome == outcome)

    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*filters)) or 0
    events = list(db.scalars(
        select(AuditEvent)
        .where(*filters)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ))

    actor_ids = {event.actor_user_id for event in events if event.actor_user_id}
    actor_emails = {}
    if actor_ids:
        actor_emails = {u.id: u.email for u in db.scalars(select(User).where(User.id.in_(actor_ids)))}

    import json
    items = []
    for event in events:
        try:
            details = json.loads(event.details or "{}")
        except (TypeError, ValueError):
            details = {"raw": event.details}
        items.append({
            "id": event.id,
            "actor_user_id": event.actor_user_id,
            "actor_email": actor_emails.get(event.actor_user_id),
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "occurred_at": ensure_utc(event.occurred_at).isoformat(),
            "correlation_id": event.correlation_id,
            "outcome": event.outcome,
            "details": details,
            "chain_sequence": event.chain_sequence,
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: str,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    actor, _ = ctx
    if actor.role not in {Role.TECHNICIAN.value, Role.OT_ADMIN.value}:
        log_event(db, actor.id, "SESSION_REVOKE_DENIED", "ACCESS_SESSION", session_id[:36],
                  "DENIED", {"reason": "ROLE_NOT_ALLOWED", "role": actor.role})
        db.commit()
        raise HTTPException(status_code=403, detail="Seu perfil não permite esta operação.")
    record = db.scalar(select(AccessSession).where(AccessSession.external_session_id == session_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    request = db.get(AccessRequest, record.access_request_id)
    if actor.role == Role.TECHNICIAN.value and request.requester_id != actor.id:
        log_event(db, actor.id, "SESSION_REVOKE_DENIED", "ACCESS_SESSION", record.id,
                  "DENIED", {"reason": "NOT_SESSION_OWNER"})
        db.commit()
        raise HTTPException(status_code=403, detail="Só é possível revogar sua própria sessão.")
    try:
        result = adapter.revoke_session(session_id, "Revogada por solicitação autorizada na ValidaOT.",
                                        f"revoke:{session_id}")
    except AdapterContractError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.error.code, "message": exc.error.message}) from exc
    record.status = result.status.value
    record.closed_at = ensure_utc(result.closed_at)
    record.status_reason = result.status_reason
    log_event(db, actor.id, "SESSION_REVOKED_SIMULATED", "ACCESS_SESSION", record.id,
              "SUCCESS", {"session_id": session_id})
    db.commit()
    return {"session_id": session_id, "status": record.status, "closed_at": record.closed_at.isoformat() if record.closed_at else None}


@app.get("/sessions")
def list_sessions(
    status_filter: Optional[str] = Query(default=None, alias="status", min_length=1, max_length=20),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """List persisted access sessions with least-privilege visibility and pagination.

    TECHNICIAN: own sessions only.
    APPROVER: sessions linked to requests on which they recorded a decision.
    OT_ADMIN/AUDITOR: all sessions (read-only).
    """
    user, _ = ctx
    require_role(user, Role.TECHNICIAN, Role.APPROVER, Role.OT_ADMIN, Role.AUDITOR)

    valid_statuses = {item.value for item in SessionState}
    if status_filter is not None and status_filter not in valid_statuses:
        raise HTTPException(status_code=422, detail={
            "message": "Status de sessão inválido.",
            "allowed_values": sorted(valid_statuses),
        })

    conditions = []
    query = select(AccessSession).join(
        AccessRequest, AccessSession.access_request_id == AccessRequest.id
    )
    count_query = select(func.count(AccessSession.id)).select_from(AccessSession).join(
        AccessRequest, AccessSession.access_request_id == AccessRequest.id
    )

    if user.role == Role.TECHNICIAN.value:
        conditions.append(AccessRequest.requester_id == user.id)
    elif user.role == Role.APPROVER.value:
        query = query.join(Approval, Approval.access_request_id == AccessRequest.id)
        count_query = count_query.join(Approval, Approval.access_request_id == AccessRequest.id)
        conditions.append(Approval.approver_id == user.id)

    if status_filter is not None:
        conditions.append(AccessSession.status == status_filter)

    total = db.scalar(count_query.where(*conditions)) or 0
    rows = list(db.scalars(
        query.where(*conditions)
        .order_by(AccessSession.valid_from.desc(), AccessSession.id.desc())
        .offset(offset)
        .limit(limit)
    ))

    request_ids = {item.access_request_id for item in rows}
    related_requests = (
        list(db.scalars(select(AccessRequest).where(AccessRequest.id.in_(request_ids))))
        if request_ids else []
    )
    request_details = {
        item["id"]: item
        for item in _serialize_access_requests(db, related_requests)
    }

    items = []
    for record in rows:
        request_detail = request_details.get(record.access_request_id, {})
        items.append({
            "id": record.id,
            "session_id": record.external_session_id,
            "external_session_id": record.external_session_id,
            "access_request_id": record.access_request_id,
            "request_code": request_detail.get("request_code"),
            "requester_id": request_detail.get("requester_id"),
            "requester_name": request_detail.get("requester_name"),
            "work_order_id": request_detail.get("work_order_id"),
            "work_order_code": request_detail.get("work_order_code"),
            "asset_id": request_detail.get("asset_id"),
            "asset_code": request_detail.get("asset_code"),
            "asset_name": request_detail.get("asset_name"),
            "asset_type": request_detail.get("asset_type"),
            "access_profile": request_detail.get("access_profile"),
            "requires_dual_approval": request_detail.get("requires_dual_approval"),
            "approved_count": request_detail.get("approved_count"),
            "required_approvals": request_detail.get("required_approvals"),
            "status": record.status,
            "adapter": record.adapter_name,
            "valid_from": ensure_utc(record.valid_from).isoformat(),
            "expires_at": ensure_utc(record.expires_at).isoformat(),
            "started_at": ensure_utc(record.started_at).isoformat() if record.started_at else None,
            "closed_at": ensure_utc(record.closed_at).isoformat() if record.closed_at else None,
            "reason": record.status_reason,
            "correlation_id": record.correlation_id,
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    ctx: tuple[User, dict] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = ctx
    record = db.scalar(select(AccessSession).where(AccessSession.external_session_id == session_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    request = db.get(AccessRequest, record.access_request_id)
    if user.role == Role.TECHNICIAN.value and request.requester_id != user.id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão.")
    try:
        sim = adapter.get_session(session_id)
        record.status = sim.status.value
        record.closed_at = ensure_utc(sim.closed_at)
        record.status_reason = sim.status_reason
        db.commit()
    except AdapterContractError:
        # Fail closed: an unknown/missing simulated session is not reported ACTIVE.
        raise HTTPException(status_code=404, detail="O adaptador não reconhece esta sessão.")
    return {"session_id": session_id, "status": record.status, "adapter": record.adapter_name,
            "expires_at": ensure_utc(record.expires_at).isoformat(), "closed_at": record.closed_at.isoformat() if record.closed_at else None,
            "reason": record.status_reason}


# The simulator instance is intentionally in memory and resets when the process restarts.
adapter = SimulatedAccessAdapter(mfa_freshness=timedelta(seconds=MFA_FRESHNESS_SECONDS),
                                 max_session_duration=timedelta(minutes=MAX_SESSION_MINUTES))
