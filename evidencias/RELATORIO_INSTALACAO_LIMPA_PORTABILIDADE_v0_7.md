# VALIDAOT v0.7
# RELATORIO DE INSTALACAO LIMPA E PORTABILIDADE

Data: 06/11/2026

## 1. OBJETIVO

Verificar se o pacote de distribuição ValidaOT v0.7 pode ser extraído,
instalado e executado em um ambiente independente do desenvolvimento
original.

O teste foi realizado sem reutilizar o banco de dados original,
as chaves privadas ou o ambiente virtual anterior.

## 2. AMBIENTE UTILIZADO

Backend: ValidaOT API 0.7.0
Front-end: ValidaOT 0.1.3 DEV
Python: 3.14.6
Banco: SQLite independente
Adaptador: SIMULATED

Backend executado em:
http://127.0.0.1:8002

Front-end executado em:
http://127.0.0.1:5175

Ambiente virtual:
backend/.venv

## 3. PREPARACAO

- ZIP de distribuição extraído em pasta independente.
- Ambiente virtual Python criado do zero.
- Dependências instaladas pelo requirements.txt.
- Integridade das dependências verificada com pip check.
- Arquivo .env próprio criado.
- Nova chave JWT gerada.
- Nova chave de criptografia MFA gerada.
- Nova senha de demonstração definida.
- Banco SQLite independente inicializado.
- Nova âncora de auditoria gerada.
- Dados fictícios criados pelo seed_demo.py.

Não foram reutilizadas as credenciais privadas ou a cadeia de auditoria
do banco original.

## 4. DADOS INICIAIS

Usuários: 5

- Técnico terceirizado.
- Aprovador 1.
- Aprovador 2.
- Administrador OT.
- Auditor OT.

Ativos: 4

- ENG-01.
- PLC-01.
- SCADA-01.
- HMI-01.

Ordens de serviço: 3

- OS-DEMO-001.
- OS-DEMO-002.
- OS-DEMO-003.

## 5. TESTES DE FUNCIONALIDADE

### 5.1 Autenticação e MFA

- Tela de login carregada.
- Conexão com a API confirmada.
- Primeiro acesso do técnico realizado.
- Configuração inicial de MFA solicitada.
- Código TOTP do Authenticator aceito.

Resultado: APROVADO.

### 5.2 Dashboard e cadastros

- Dashboard apresentou zero sessões ativas.
- Quatro ativos OT exibidos.
- Três ordens de serviço exibidas.

Resultado: APROVADO.

### 5.3 Aprovação simples

Ordem: OS-DEMO-001
Ativo: ENG-01
Criticidade do ativo: HIGH
Criticidade da ordem: Não crítica.

Solicitação: REQ-51E132737E
Aprovação: 1/1
Sessão: SIM-SESSION-000001

A sessão foi criada e posteriormente revogada.
O indicador retornou a zero sessões ativas.

Resultado: APROVADO.

### 5.4 Aprovação dupla por ativo crítico

Ordem: OS-DEMO-002
Ativo: PLC-01
Criticidade do ativo: CRITICAL.
Criticidade da ordem: Não crítica.

Solicitação: REQ-195C170877
Aprovação: 2/2
Sessão: SIM-SESSION-000002

Dois aprovadores distintos participaram.
A sessão foi criada e posteriormente revogada.
O indicador retornou a zero sessões ativas.

Resultado: APROVADO.

### 5.5 Aprovação dupla por ordem crítica

Ordem: OS-DEMO-003
Ativo: SCADA-01
Criticidade do ativo: HIGH.
Criticidade da ordem: CRITICAL.

Solicitação: REQ-7360863988
Aprovação: 2/2
Sessão: SIM-SESSION-000003

A primeira decisão deixou a solicitação aguardando aprovação.
A segunda decisão concluiu a aprovação.
A sessão foi criada e posteriormente revogada.

O indicador retornou a zero sessões ativas.

Resultado: APROVADO.

## 6. PERFIL AUDITOR OT

Foram confirmados:
- Consulta da trilha de auditoria.
- Consulta dos eventos registrados.
- Consulta de sessões.
- Acesso somente para consulta na interface.
- Ausência de ações de aprovação e revogação.

Resultado: APROVADO.

## 7. INTEGRIDADE DA AUDITORIA

Verificação final:

VERIFICACAO DE INTEGRIDADE DEV: OK

Eventos verificados: 29
Última sequência: 29

Hash da âncora DEV:

aa620e4475f1c8db6f46722a33e7c3ad7f5baf3b73db812026bbf0d84aba7792

Cabeça da cadeia:

7f9920d3c7da97bfa426e71411a00b5c1ce08e18cdd3201f0c8632859b0bb1ea

Baseline oficial: NÃO UTILIZADO.
Modo de verificação: SOMENTE LEITURA.

Resultado: INTEGRIDADE APROVADA.

## 8. BACKUP DA INSTALACAO LIMPA

Arquivo:

validaot_instalacao_limpa_pre_portabilidade_20261106_140339.db

Integridade SQLite: OK.

Eventos: 29.
Sessões: 3.
Solicitações: 3.

SHA-256:

3c28aebc68563940873e67b945735dcce57b9c1f3565bd38feae219bdbdee46f

O backup foi comparado logicamente com o banco de origem.

Resultado: APROVADO.

## 9. RESULTADO DA PORTABILIDADE

Foi comprovado que o pacote de distribuição pode ser extraído
e executado em uma instalação independente no computador de desenvolvimento.

O ambiente novo utilizou:
- Python 3.14.6.
- Ambiente virtual próprio.
- Dependências instaladas separadamente.
- Banco SQLite novo.
- Chaves de segurança próprias.
- Nova âncora de auditoria.

Os três cenários de criticidade foram reproduzidos com sucesso.

### Limitação da validação

Este teste foi executado em uma instalação isolada no mesmo computador.

Ainda é necessário repetir a instalação em um segundo computador
físico para comprovar a portabilidade entre máquinas diferentes.

## 10. CONCLUSAO

A instalação independente do ValidaOT v0.7 apresentou funcionamento
satisfatório nos testes realizados.

Foram validados autenticação, MFA, solicitações, aprovações simples,
aprovações duplas, autorização, sessões simuladas, revogação,
consulta pelo Auditor e integridade da cadeia de auditoria.

O protótipo permanece destinado à demonstração acadêmica.

Não existe conexão com equipamentos SCADA, IHM, CLPs ou redes OT reais.
Não existe integração com inteligência artificial.

Este relatório não representa homologação industrial ou certificação
de segurança.
