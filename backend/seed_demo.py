"""Create demo accounts, a fictional industrial site, assets and work orders.
Run only in a local development database: python seed_demo.py
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from sqlalchemy import select
from main import (Base, engine, SessionLocal, Company, User, IndustrialSite, Asset,
                  WorkOrder, Role, password_hasher)

load_dotenv()
password = os.getenv("DEMO_PASSWORD")
if not password or password.startswith("Change-This"):
    raise SystemExit("Defina uma DEMO_PASSWORD própria no arquivo .env antes de executar o seed_demo.py.")
Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    industry = db.scalar(select(Company).where(Company.name == "Indústria Alfa (DEMO)"))
    if not industry:
        industry = Company(name="Indústria Alfa (DEMO)", company_type="INDUSTRY", status="ACTIVE")
        contractor = Company(name="Serviços OT (DEMO)", company_type="CONTRACTOR", status="ACTIVE")
        db.add_all([industry, contractor]); db.flush()
    else:
        contractor = db.scalar(select(Company).where(Company.name == "Serviços OT (DEMO)"))
        if not contractor:
            contractor = Company(name="Serviços OT (DEMO)", company_type="CONTRACTOR", status="ACTIVE")
            db.add(contractor); db.flush()

    def get_or_create_user(email, name, role, company):
        # Migrate early demo accounts away from the reserved .local suffix rejected by EmailStr.
        legacy_email = email.replace("@validaot.com", "@validaot.local")
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = db.scalar(select(User).where(User.email == legacy_email))
            if user:
                user.email = email
                user.company_id = company.id
                user.full_name = name
                user.role = role.value
                user.status = "ACTIVE"
                db.flush()
        if not user:
            user = User(company_id=company.id, full_name=name, email=email,
                        password_hash=password_hasher.hash(password), role=role.value, status="ACTIVE")
            db.add(user); db.flush()
        return user

    technician = get_or_create_user("tecnico@validaot.com", "Carlos Mendes (DEMO)", Role.TECHNICIAN, contractor)
    approver1 = get_or_create_user("aprovador1@validaot.com", "Marina Costa (DEMO)", Role.APPROVER, industry)
    get_or_create_user("aprovador2@validaot.com", "Rafael Lima (DEMO)", Role.APPROVER, industry)
    get_or_create_user("admin@validaot.com", "Administrador OT (DEMO)", Role.OT_ADMIN, industry)
    get_or_create_user("auditor@validaot.com", "Auditor (DEMO)", Role.AUDITOR, industry)

    site = db.scalar(select(IndustrialSite).where(IndustrialSite.owner_company_id == industry.id,
                                                  IndustrialSite.code == "SITE-01"))
    if not site:
        site = IndustrialSite(owner_company_id=industry.id, code="SITE-01", name="Planta de Demonstração",
                              timezone_name="America/Recife", status="ACTIVE")
        db.add(site); db.flush()

    def get_or_create_asset(code, name, typ, crit, gateway_ref):
        asset = db.scalar(select(Asset).where(Asset.site_id == site.id, Asset.asset_code == code))
        if not asset:
            asset = Asset(site_id=site.id, asset_code=code, name=name, asset_type=typ,
                          criticality=crit, gateway_ref=gateway_ref, status="ACTIVE")
            db.add(asset); db.flush()
        return asset

    eng = get_or_create_asset("ENG-01", "Estação de Engenharia 01", "ENGINEERING_STATION", "HIGH", "SIM-ENG-01")
    plc = get_or_create_asset("PLC-01", "CLP da Linha de Embalagem", "PLC", "CRITICAL", "SIM-PLC-01")
    scada = get_or_create_asset("SCADA-01", "Servidor SCADA 01", "SCADA_SERVER", "HIGH", "SIM-SCADA-01")
    get_or_create_asset("HMI-01", "IHM da Linha 01", "HMI", "MEDIUM", "SIM-HMI-01")

    now = datetime.now(timezone.utc)
    orders = [
        ("OS-DEMO-001", eng, False, "Diagnóstico na estação de engenharia"),
        ("OS-DEMO-002", plc, False, "Manutenção programada do CLP crítico"),
        ("OS-DEMO-003", scada, True, "Intervenção crítica no servidor SCADA"),
    ]
    for code, asset, is_critical, desc in orders:
        existing = db.scalar(select(WorkOrder).where(WorkOrder.code == code))
        if not existing:
            db.add(WorkOrder(code=code, site_id=site.id, asset_id=asset.id,
                             assigned_technician_id=technician.id, responsible_user_id=approver1.id,
                             planned_start_at=now - timedelta(hours=1), planned_end_at=now + timedelta(hours=8),
                             is_critical=is_critical, status="OPEN", description=desc))
    db.commit()
    print("Dados de demonstração criados/confirmados.")
    print("Técnico: tecnico@validaot.com")
    print("Aprovadores: aprovador1@validaot.com / aprovador2@validaot.com")
    print("Administrador: admin@validaot.com | Auditor: auditor@validaot.com")
    print("Use a DEMO_PASSWORD definida no seu .env. O técnico será solicitado a configurar TOTP no primeiro login.")
finally:
    db.close()
