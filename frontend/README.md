# ValidaOT Frontend — Distribuição 0.7.1

Interface web do ValidaOT, integrada ao backend FastAPI 0.7.0. Esta atualização incorpora a identidade visual oficial ValidaOT sem alterar os fluxos funcionais da interface.

![Logo ValidaOT](assets/logo_validaot_completa.webp)

## Identidade visual

- `assets/logo_validaot_simbolo.webp`: emblema compacto usado no login, MFA, barra lateral e marca de carregamento.
- `assets/logo_validaot_completa.webp`: composição completa da marca para documentação e materiais do projeto.
- `assets/favicon_validaot.png`: ícone da aba do navegador.

## Execução recomendada

Na raiz do pacote, execute `iniciar_validaot.bat`. O inicializador abre o backend em `127.0.0.1:8002`, aguarda a porta ficar disponível e depois abre o frontend em `127.0.0.1:5175`.

## Execução manual

Com o backend iniciado, abra PowerShell nesta pasta e execute:

```powershell
..\backend\.venv\Scripts\python.exe .\dev_server.py --host 127.0.0.1 --port 5175 --backend http://127.0.0.1:8002
```

Acesse `http://127.0.0.1:5175`.

O servidor usa proxy same-origin em `/api/*`, não registra credenciais ou corpos de requisição no log e escuta somente em loopback por padrão. Não exponha o servidor na rede.

## Funcionalidades

A interface apresenta funcionalidades conforme o perfil autenticado: Técnico, Aprovador, Administrador OT e Auditor. As operações reais dependem do backend. O modo de pré-visualização usa dados sintéticos e não substitui a autenticação nem os dados retornados pelo backend.

## Limitação

O adaptador industrial é `SIMULATED`. Não há comunicação com equipamentos SCADA, IHM, CLPs ou redes OT reais.
