# ValidaOT Backend 0.7.0

Backend FastAPI do pacote acadêmico ValidaOT 0.7.1. A versão da API permanece 0.7.0; a release 0.7.1 atualiza a identidade visual e a documentação do pacote.

## Arquivos principais

- `main.py`
- `validaot_adapter_contract.py`
- `audit_integrity_common.py`
- `requirements.txt`
- `requirements-lock-py314-win64.txt`
- `gerar_config_demo.py`
- `initialize_dev_audit.py`
- `seed_demo.py`
- `seed_demo_seguro.py`
- `verify_dev_audit.py`

## Instalação

Siga as instruções do `README.md` na raiz do pacote. Utilize Windows 64 bits, Python 3.14 de 64 bits e as versões fixadas em `requirements-lock-py314-win64.txt`.

## Ordem de inicialização

1. Criar o ambiente virtual.
2. Instalar as dependências.
3. Gerar a configuração privada.
4. Inicializar a auditoria.
5. Criar os dados de demonstração.
6. Iniciar o backend.

## Proteções

O banco deve ser SQLite exclusivo do ambiente DEV. O inicializador recusa banco ou manifesto já existentes; o seed seguro recusa tabelas de dados já populadas. Não execute novamente os scripts de inicialização em uma instalação já preparada.

Não compartilhe o arquivo `.env`, chaves privadas ou bancos com credenciais.

## Limitações

O adaptador industrial é simulado. Não há integração com equipamentos ou redes OT reais. O backend não possui integração com IA.
