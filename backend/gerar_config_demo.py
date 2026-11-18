from pathlib import Path
from secrets import token_urlsafe
from cryptography.fernet import Fernet

root = Path.cwd()

jwt_secret = token_urlsafe(48)
mfa_key = Fernet.generate_key().decode()
demo_password = "ValidaOT-" + token_urlsafe(18) + "!"

Fernet(mfa_key)

content = f"""APP_ENV=development
APP_NAME="ValidaOT API DEMO"
DATABASE_URL=sqlite:///./validaot_dev_v013.db
JWT_SECRET_KEY={jwt_secret}
MFA_ENCRYPTION_KEY={mfa_key}
TOTP_ISSUER="ValidaOT DEMONSTRACAO"
ACCESS_TOKEN_MINUTES=30
MFA_CHALLENGE_MINUTES=10
MFA_FRESHNESS_SECONDS=600
MFA_SETUP_TTL_MINUTES=10
MFA_MAX_FAILED_ATTEMPTS=5
MFA_LOCKOUT_MINUTES=10
MAX_SESSION_MINUTES=120
DEMO_PASSWORD={demo_password}
"""

env_path = root / ".env"

if env_path.exists():
    raise RuntimeError(".env já existe. Nenhum arquivo foi sobrescrito.")

env_path.write_text(content, encoding="utf-8")

print("CONFIGURACAO PRIVADA CRIADA.")
print("Ambiente: development")
print("Banco: validaot_dev_v013.db")
print("JWT: chave nova gerada.")
print("MFA: chave Fernet nova validada.")
print("Senha de demonstração:", demo_password)
print("Arquivo:", env_path)
print("\nGUARDE A SENHA DE DEMONSTRACAO EM LOCAL SEGURO.")
