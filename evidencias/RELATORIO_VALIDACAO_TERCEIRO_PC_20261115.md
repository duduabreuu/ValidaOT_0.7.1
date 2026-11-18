# RELATÓRIO DE VALIDAÇÃO — TERCEIRO COMPUTADOR FÍSICO

**Projeto:** ValidaOT
**Pacote base testado:** Distribuição acadêmica v0.7.0
**Backend/API:** 0.7.0
**Data informada dos testes:** 15/11/2026
**Ambiente:** Windows, instalação independente em terceiro computador físico
**Adaptador industrial:** `SIMULATED`

## 1. Objetivo

Registrar a validação de portabilidade e dos fluxos funcionais do ValidaOT em um terceiro computador físico, sem reutilizar o banco SQLite, as chaves privadas ou a cadeia de auditoria das instalações anteriores.

## 2. Verificações da instalação

- Instalação do pacote concluída em diretório independente.
- Banco SQLite próprio criado: `backend/validaot_dev_v013.db`.
- Cadeia de auditoria própria, com âncora SHA-256: `ebc7db6f0e9f026d7142635296f4d9daa611a2ac7e793e90da8734e3badba8c4`.
- Verificação inicial da auditoria: 0 eventos, sequência 0, resultado `VERIFICACAO DE INTEGRIDADE DEV: OK`.
- `pip check`: `No broken requirements found.`
- Backend e frontend iniciados; interface abriu no navegador e indicou API conectada.

## 3. Testes funcionais

### 3.1 Autenticação e MFA

O login do técnico foi realizado. O sistema solicitou a configuração/validação MFA e aceitou o código TOTP gerado pelo aplicativo autenticador.

**Resultado informado:** aprovado.

### 3.2 OS-DEMO-001 — uma aprovação

- Ativo: `ENG-01` — Estação de Engenharia 01.
- Perfil: Diagnóstico.
- Solicitação: `REQ-FF76ABF4C0`.
- Aprovação: 1/1.
- Sessão: `SIM-SESSION-000001`, adaptador `SIMULATED`.
- A sessão foi exibida como ativa e posteriormente revogada.
- O dashboard retornou a zero sessões ativas.

**Resultado informado:** aprovado.

### 3.3 OS-DEMO-002 — ativo crítico

- Ativo: `PLC-01`, criticidade `CRITICAL`.
- Perfil: `MAINTENANCE`.
- Duas aprovações exigidas.
- Primeira aprovação: 1/2.
- Segunda aprovação: 2/2.
- Sessão: `SIM-SESSION-000002`, criada e posteriormente revogada.

**Resultado informado:** aprovado.

### 3.4 OS-DEMO-003 — ordem de serviço crítica

- Ativo: `SCADA-01`, criticidade `HIGH`.
- Ordem de serviço crítica.
- Perfil: `MAINTENANCE`.
- Duas aprovações exigidas e realizadas: 2/2.
- Sessão: `SIM-SESSION-000003`, criada e posteriormente revogada.

**Resultado informado:** aprovado.

## 4. Estado final das sessões

A consulta somente leitura à tabela `access_sessions` confirmou os seguintes estados:

| Sessão | Estado final |
|---|---|
| `SIM-SESSION-000001` | `REVOKED` |
| `SIM-SESSION-000002` | `REVOKED` |
| `SIM-SESSION-000003` | `REVOKED` |

Os registros continham `closed_at` preenchido e motivo de revogação: “Revogada por solicitação autorizada na ValidaOT.”

## 5. Integridade final da auditoria

A verificação final apresentou:

```text
VERIFICACAO DE INTEGRIDADE DEV: OK
Eventos verificados: 25
Eventos de gênese: 0
Última sequência: 25
Hash âncora DEV: ebc7db6f0e9f026d7142635296f4d9daa611a2ac7e793e90da8734e3badba8c4
Cabeça atual da cadeia: 170fa6d5c91c86bf44d90c5d354a66fdf1d2ea2a64954cf8d5cec1f42ef8dfba
Modo: somente leitura; banco não foi alterado.
Baseline oficial: NÃO UTILIZADO.
```

A consulta aos seis eventos mais recentes mostrou a concessão da sessão 3 na sequência 24 e sua revogação na sequência 25, vinculadas ao mesmo `entity_id`.

## 6. Conclusão e limites

Os testes relatados confirmam a execução independente do ValidaOT em um terceiro computador físico e a reprodução dos três cenários de aprovação. A cadeia de auditoria foi verificada com 25 eventos, e as três sessões de demonstração terminaram revogadas.

Esta validação corresponde a um protótipo acadêmico. O adaptador é `SIMULATED`; não houve conexão com equipamentos SCADA, IHM, CLPs ou redes OT reais. Os resultados não constituem certificação, auditoria independente ou homologação industrial.
