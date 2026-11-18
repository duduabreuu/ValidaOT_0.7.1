# VALIDAOT v0.7 DEV
# RELATORIO DE TESTES FUNCIONAIS

Data de fechamento: 05/11/2026

## 1. IDENTIFICACAO DO AMBIENTE

Backend: ValidaOT API 0.7.0
Front-end: ValidaOT 0.1.3 DEV
Banco de dados: SQLite DEV
Arquivo do banco: validaot_dev_v013.db
Adaptador industrial: SIMULATED
Ambiente: Desenvolvimento acadêmico

Não foi realizada conexão com equipamentos ou redes OT reais.

## 2. PERFIS FUNCIONAIS TESTADOS

### 2.1 Técnico terceirizado

Foram verificados:
- Autenticação por e-mail e senha.
- Configuração e verificação do MFA TOTP.
- Criação de solicitações de acesso.
- Consulta de solicitações.
- Autorização após aprovação.
- Consulta de sessões.
- Revogação de sessões.
- Atualização do indicador de sessões ativas.

Resultado: funcionalidades verificadas com sucesso nos cenários executados.

### 2.2 Aprovador industrial

Foram verificados:
- Login do primeiro aprovador.
- Login do segundo aprovador.
- Aprovação simples.
- Aprovação dupla por usuários distintos.
- Permanência da solicitação pendente após a primeira decisão no fluxo de aprovação dupla.
- Conclusão da aprovação após a segunda decisão.

Resultado: cenários executados com sucesso.

### 2.3 Administrador OT

Foram verificados:
- Autenticação.
- Consulta de ativos.
- Consulta de solicitações.
- Consulta de sessões.
- Consulta da trilha de auditoria.
- Indicadores do dashboard.

Resultado: funcionalidades verificadas com sucesso nos cenários executados.

### 2.4 Auditor OT

Foram verificados:
- Consulta de sessões.
- Consulta de sessões revogadas.
- Consulta dos eventos da trilha de auditoria.
- Ausência de ações de aprovação, autorização e revogação na interface.

Resultado: comportamento de consulta somente leitura confirmado na interface.

## 3. TESTES DAS REGRAS DE CRITICIDADE

### CENÁRIO A — ATIVO CRÍTICO

Ordem de serviço: OS-DEMO-002
Ativo: PLC-01
Tipo: CLP
Criticidade do ativo: CRITICAL
Criticidade da ordem: Não crítica
Aprovações exigidas: 2

Solicitação: REQ-02ABEE5F0F
Sessão: SIM-SESSION-000001

Resultado:
- Duas aprovações de usuários distintos realizadas.
- Solicitação aprovada.
- Sessão simulada criada.
- Consulta e revogação testadas.

Resultado do cenário: APROVADO.

### CENÁRIO B — ORDEM DE SERVIÇO CRÍTICA

Ordem de serviço: OS-DEMO-003
Ativo: SCADA-01
Tipo: Servidor SCADA
Criticidade do ativo: HIGH
Criticidade da ordem: Crítica
Aprovações exigidas: 2

Solicitação: REQ-450C540638
Sessão: SIM-SESSION-000002

Evidência da regra:
criticality_reason = WORK_ORDER_CRITICAL
requires_dual_approval = true

Resultado:
- Duas aprovações de usuários distintos realizadas.
- Solicitação aprovada.
- Sessão simulada criada.
- Consulta e revogação testadas.

Resultado do cenário: APROVADO.

### CENÁRIO C — ATIVO E ORDEM NÃO CRÍTICOS

Ordem de serviço: OS-DEMO-001
Ativo: ENG-01
Tipo: Estação de Engenharia
Criticidade do ativo: HIGH
Criticidade da ordem: Não crítica
Aprovações exigidas: 1

Solicitação: REQ-FF7A9655B5
Sessão: SIM-SESSION-000003

Evidência da regra:
criticality_reason = NONE
requires_dual_approval = false

Resultado:
- Uma aprovação realizada.
- Solicitação aprovada.
- Sessão simulada criada.
- Consulta e revogação testadas.

Resultado do cenário: APROVADO.

## 4. TESTES DE SESSÕES

Foram criadas três sessões simuladas:

SIM-SESSION-000001
SIM-SESSION-000002
SIM-SESSION-000003

As três sessões foram posteriormente revogadas.

Foi verificado que:
- Sessões ativas aparecem no dashboard do Técnico.
- A revogação remove a sessão da contagem de sessões ativas.
- Sessões revogadas continuam disponíveis para consulta.
- O botão de revogação não aparece para sessões já revogadas.
- O perfil Auditor consegue consultar o histórico.

Resultado: cenários executados com sucesso.

## 5. TRILHA DE AUDITORIA E INTEGRIDADE

Última verificação realizada em 05/11/2026.

Resultado:
VERIFICACAO DE INTEGRIDADE DEV: OK

Eventos verificados: 35
Última sequência: 35
Integridade da cadeia: OK
Baseline oficial: NÃO UTILIZADO
Modo de verificação: Somente leitura

Hash da âncora DEV:

4273823079d392db7781097f9154a28a7237258c46aa85b6924bf7418447ca52

Cabeça da cadeia no fechamento:

c82cb12f9c6e7d1acb089df7b3baeeb18935cc05d155b33ce100921f61503778

Eventos importantes verificados:
- WORK_ORDER_SCHEDULE_UPDATED
- ACCESS_REQUEST_SUBMITTED
- ACCESS_REQUEST_DECISION
- SESSION_GRANTED_SIMULATED
- SESSION_REVOKED_SIMULATED

Resultado: integridade validada.

## 6. BACKUP DE FECHAMENTO

Arquivo:

validaot_dev_v013_pre_consolidation_20261105_112624.db

Integridade SQLite: OK

Eventos preservados: 35
Sessões registradas: 3
Solicitações registradas: 3

SHA-256:

a2b61b2b06544dc99f52f21e6bfc62967bfa7fe1f66d5cb1c63bbd4d92673184

## 7. LIMITACOES DO PROTOTIPO

- O adaptador industrial é simulado.
- Não existe comunicação com equipamentos SCADA, IHM ou CLPs reais.
- Não existe conexão com redes industriais OT.
- Não existe integração com inteligência artificial.
- O banco SQLite utilizado é destinado ao ambiente DEV.
- Os testes executados não representam certificação de segurança.
- O sistema não está homologado para produção industrial.

Uma implantação real exigiria avaliações adicionais de segurança,
infraestrutura, integração, disponibilidade e continuidade operacional.

## 8. CONCLUSAO

Os três cenários de criticidade foram executados com sucesso:

1. Ativo crítico exigindo duas aprovações.
2. Ordem de serviço crítica exigindo duas aprovações.
3. Ativo e ordem não críticos exigindo uma aprovação.

Também foram executados testes de autenticação MFA, autorização,
criação e revogação de sessões, permissões por perfil e consulta
da trilha de auditoria.

A cadeia de auditoria apresentou resultado íntegro, com 35 eventos
verificados até o fechamento desta bateria de testes.

O ValidaOT v0.7 DEV apresenta os fluxos funcionais descritos
validados no ambiente acadêmico de desenvolvimento.

Este relatório não representa homologação para produção industrial.
