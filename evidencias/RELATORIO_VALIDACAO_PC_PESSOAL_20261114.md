# VALIDAOT v0.7.0 â€” RELATÃ“RIO DE VALIDAÃ‡ÃƒO NO COMPUTADOR PESSOAL

Data: 14/11/2026
Backend: ValidaOT API 0.7.0
Frontend: interface integrada pelo proxy same-origin
Python: 3.14.8 (64 bits, conforme ambiente virtual utilizado)
Banco: SQLite DEV independente
Adaptador: SIMULATED

## 1. PreparaÃ§Ã£o

- Ambiente virtual prÃ³prio utilizado.
- `pip check` concluÃ­do sem problemas.
- ConfiguraÃ§Ã£o `.env` prÃ³pria gerada localmente.
- Banco `validaot_dev_v013.db` inicializado localmente.
- Cadeia de auditoria DEV inicializada com Ã¢ncora prÃ³pria.
- Carga demonstrativa concluÃ­da: 2 empresas, 5 usuÃ¡rios, 1 instalaÃ§Ã£o industrial, 4 ativos e 3 ordens de serviÃ§o.
- Backend iniciado em `127.0.0.1:8002`.
- Frontend iniciado em `127.0.0.1:5175`.
- API conectada Ã  interface.

## 2. AutenticaÃ§Ã£o e MFA

O primeiro acesso de `tecnico@validaot.com` foi realizado. A configuraÃ§Ã£o TOTP foi concluÃ­da e o cÃ³digo do aplicativo autenticador foi aceito.

Resultado: APROVADO.

## 3. CenÃ¡rios de aprovaÃ§Ã£o

### OS-DEMO-001 â€” uma aprovaÃ§Ã£o

- Ativo: ENG-01.
- Perfil solicitado: DIAGNOSTIC.
- SolicitaÃ§Ã£o: REQ-6A5D7400B4.
- AprovaÃ§Ã£o: 1/1.
- SessÃ£o simulada criada e posteriormente revogada.

Resultado: APROVADO.

### OS-DEMO-002 â€” ativo crÃ­tico

- Ativo: PLC-01.
- Criticidade do ativo: CRITICAL.
- Ordem nÃ£o marcada como crÃ­tica.
- Perfil solicitado: MAINTENANCE.
- SolicitaÃ§Ã£o: REQ-AA5805299A.
- AprovaÃ§Ãµes: 2/2, por Marina Costa e Rafael Lima.
- Motivo retornado pelo backend: `ASSET_CRITICAL`.
- SessÃ£o `SIM-SESSION-000002` criada e posteriormente revogada.

Resultado: APROVADO.

### OS-DEMO-003 â€” ordem de serviÃ§o crÃ­tica

- Ativo: SCADA-01.
- Criticidade do ativo: HIGH.
- Ordem de serviÃ§o crÃ­tica.
- Perfil solicitado: MAINTENANCE.
- SolicitaÃ§Ã£o: REQ-CA0506C260.
- AprovaÃ§Ãµes: 2/2, por Marina Costa e Rafael Lima.
- Motivo retornado pelo backend: `WORK_ORDER_CRITICAL`.
- SessÃ£o `SIM-SESSION-000003` criada e posteriormente revogada.

Resultado: APROVADO.

## 4. SessÃµes e revogaÃ§Ã£o

As trÃªs sessÃµes demonstrativas (`SIM-SESSION-000001`, `SIM-SESSION-000002` e `SIM-SESSION-000003`) foram confirmadas no SQLite com status `REVOKED`.

A consulta dos eventos mostrou o evento `SESSION_REVOKED_SIMULATED` para a terceira sessÃ£o na sequÃªncia 24.

Resultado: APROVADO.

## 5. Integridade da auditoria

Verificador: `verify_dev_audit.py`

Resultado: `VERIFICACAO DE INTEGRIDADE DEV: OK`

- Eventos verificados: 24.
- Ãšltima sequÃªncia: 24.
- Eventos de gÃªnese: 0.
- Hash da Ã¢ncora DEV: `29271e42c46babfbd484c53e9a801a14f4932df630c0db359c9af74689293be5`.
- CabeÃ§a atual da cadeia: `d2f2c65995270e9f27f725605d4d5470ac752b6e7f86dceca083ccb91624d798`.
- Modo do verificador: somente leitura.
- Baseline oficial: nÃ£o utilizado.

Resultado: INTEGRIDADE APROVADA.

## 6. Limites desta validaÃ§Ã£o

Esta validaÃ§Ã£o foi realizada no computador pessoal, em uma instalaÃ§Ã£o prÃ³pria distinta do ambiente de trabalho. Ela nÃ£o substitui a instalaÃ§Ã£o e os testes em um terceiro computador fÃ­sico, que permanecem como etapa de comprovaÃ§Ã£o da distribuiÃ§Ã£o entre mÃ¡quinas.

Os dados sÃ£o demonstrativos. O adaptador industrial Ã© simulado. NÃ£o houve comunicaÃ§Ã£o com equipamentos SCADA, IHM, CLPs ou redes OT reais. Este relatÃ³rio nÃ£o representa homologaÃ§Ã£o ou certificaÃ§Ã£o para produÃ§Ã£o industrial.