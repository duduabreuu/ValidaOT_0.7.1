# ValidaOT v0.7.1 — Pacote de distribuição acadêmica

![ValidaOT — Segurança e Controle para o Ambiente Industrial](frontend/assets/logo_validaot_completa.webp)

O ValidaOT é um protótipo acadêmico para controle de acesso de técnicos terceirizados a ativos de tecnologia operacional (OT). O projeto demonstra autenticação, MFA TOTP, aprovação de solicitações, sessões simuladas e trilha de auditoria.

**Esta release 0.7.1 incorpora a identidade visual oficial do ValidaOT.** A API backend permanece na versão 0.7.0; a alteração de versão do pacote corresponde à atualização visual, aos ativos de marca e à documentação. Os fluxos funcionais de autenticação, aprovação, sessões e auditoria não foram redesenhados nesta atualização.

## 1. Escopo e limitações

- Adaptador industrial `SIMULATED`.
- Sem conexão com equipamentos SCADA, IHM, CLPs ou redes OT reais.
- Sem integração com inteligência artificial.
- Protótipo destinado à demonstração acadêmica; não homologado para produção industrial.

## 2. Requisitos

- Windows 10/11 de 64 bits.
- Python 3.14 de 64 bits e Python Launcher (`py`). A instalação limpa anterior foi testada com Python 3.14.6; a instalação no computador pessoal foi validada com Python 3.14.8.
- Internet durante a instalação das dependências.
- Navegador moderno.

Após a instalação, a demonstração local não precisa de internet para executar a aplicação, desde que as dependências já estejam instaladas.

## 3. Instalação inicial — executar uma única vez

1. Extraia todo o conteúdo do ZIP para uma pasta local, por exemplo `C:\ValidaOT`.
2. Abra o PowerShell nessa pasta.
3. Execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_validaot.ps1
```

O instalador verifica o Python, cria `backend\.venv`, instala as versões fixadas, executa `pip check`, gera um `.env` privado com chaves próprias, inicializa um banco SQLite e uma nova âncora de auditoria e cria os dados demonstrativos.

**Guarde a `DEMO_PASSWORD` exibida durante a instalação.** A mesma senha inicial é usada pelas cinco contas. Não compartilhe a senha nem o arquivo `backend\.env`.

Não execute novamente o instalador em uma instalação já preparada. Os inicializadores recusam substituir banco, manifesto ou configuração existentes.

## 4. Verificação dos arquivos distribuídos

Execute esta verificação logo após extrair o ZIP e **antes** de instalar as dependências:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\verificar_integridade_distribuicao.ps1
```

O verificador compara os arquivos com `MANIFEST_SHA256.txt` e procura arquivos privados ou gerados indevidamente no pacote limpo. Depois da instalação, a pasta `.venv`, o `.env`, o banco, o manifesto de gênese e caches Python são arquivos locais esperados; por isso, a verificação da distribuição deve ser feita antes do instalador.

## 5. Iniciar a aplicação

Depois que a instalação terminar, execute na pasta principal:

```powershell
.\iniciar_validaot.bat
```

Serão abertas janelas separadas para backend e frontend. Mantenha ambas abertas durante a demonstração.

- Frontend: `http://127.0.0.1:5175`
- Backend local: `http://127.0.0.1:8002`

O acesso para a apresentação é feito pelo endereço do frontend. Os servidores escutam somente em `127.0.0.1`; a aplicação é acessada no próprio computador, não diretamente pelos celulares dos participantes.

Para encerrar, pressione `Ctrl+C` em cada janela dos servidores. Não apague o banco, o `.env` ou o manifesto de auditoria para encerrar a aplicação.

## 6. Contas demonstrativas

| Perfil | E-mail |
|---|---|
| Técnico terceirizado | `tecnico@validaot.com` |
| Aprovador 1 | `aprovador1@validaot.com` |
| Aprovador 2 | `aprovador2@validaot.com` |
| Administrador OT | `admin@validaot.com` |
| Auditor OT | `auditor@validaot.com` |

Todas usam inicialmente a `DEMO_PASSWORD` gerada no computador de destino. No primeiro acesso do técnico, configure o MFA TOTP com um aplicativo autenticador. Não reutilize o `.env` de outro computador.

## 7. Cenários demonstrativos

1. `OS-DEMO-001` / `ENG-01`: uma aprovação.
2. `OS-DEMO-002` / `PLC-01`: duas aprovações porque o ativo é `CRITICAL`.
3. `OS-DEMO-003` / `SCADA-01`: duas aprovações porque a ordem de serviço é crítica, embora o ativo seja `HIGH`.

A regra de dupla aprovação é acionada quando o ativo **ou** a ordem de serviço é crítica.

## 8. Verificação da cadeia de auditoria

Após a instalação, execute:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe .\verify_dev_audit.py
```

O verificador abre o banco em modo somente leitura. A sequência e a quantidade de eventos aumentam conforme a utilização do sistema.

## 9. Evidências de validação

A pasta `evidencias` contém relatórios históricos de testes realizados em instalações distintas. Os números de eventos, hashes, solicitações e sessões de cada relatório pertencem à respectiva instalação e não devem ser somados ou tratados como um único banco.

A instalação independente foi concluída em um terceiro computador físico. Nesse equipamento, foram repetidos login e MFA TOTP, os três cenários de aprovação, criação e revogação de sessões e a verificação final da cadeia de auditoria. O verificador confirmou 25 eventos e a última sequência 25; as três sessões demonstrativas terminaram com status `REVOKED`. Consulte `evidencias/RELATORIO_VALIDACAO_TERCEIRO_PC_20261115.md`.

## 10. Segurança e privacidade

Não distribua nem compartilhe `backend\.env`, `backend\validaot_dev_v013.db`, `backend\audit_dev_genesis.json` ou a pasta `backend\.venv`. Esses arquivos são criados localmente e contêm configuração, dados ou estado específico da instalação. O ZIP de distribuição não inclui esses itens.

O manifesto `MANIFEST_SHA256.txt` permite verificar se os arquivos distribuídos foram alterados após sua geração. A release 0.7.0 original permanece preservada separadamente com seu próprio SHA-256; esta release 0.7.1 possui manifesto e hash próprios.
