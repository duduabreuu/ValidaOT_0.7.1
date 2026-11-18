(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const app = $('#app');
  const toastRegion = $('#toast-region');
  const AUTH_KEY = 'validaot.auth.v1';
  const SESSIONS_KEY = 'validaot.sessions.v1';

  const state = {
    token: null,
    user: null,
    mfaVerifiedAt: null,
    challengeToken: null,
    challengeMode: null,
    pendingAuthorization: null,
    view: 'dashboard',
    mobileNavOpen: false,
    online: false,
    data: { assets: [], orders: [], requests: [], events: [], sessions: [], sessionsTotal: 0, sessionsActiveTotal: 0 },
    sessions: safeJson(sessionStorage.getItem(SESSIONS_KEY), []),
    loading: false,
    preview: false,
    realSessionsBeforePreview: null,
  };

  function safeJson(value, fallback) {
    try { return value ? JSON.parse(value) : fallback; } catch { return fallback; }
  }
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  }
  function initials(name) {
    return String(name || 'ValidaOT').trim().split(/\s+/).slice(0, 2).map(x => x[0] || '').join('').toUpperCase();
  }
  function roleLabel(role) {
    return ({ TECHNICIAN:'Técnico terceirizado', APPROVER:'Aprovador industrial', OT_ADMIN:'Administrador OT', AUDITOR:'Auditor' })[role] || role || 'Usuário';
  }
  function statusLabel(status) {
    return ({ PENDING_APPROVAL:'Aguardando aprovação', APPROVED:'Aprovada', REJECTED:'Recusada', CANCELLED:'Cancelada', EXPIRED:'Expirada', ACTIVE:'Ativa', PROVISIONING:'Provisionando', REVOKING:'Revogando', REVOKED:'Revogada', FAILED:'Falha', CLOSED:'Encerrada', OPEN:'Aberta', IN_PROGRESS:'Em andamento', COMPLETED:'Concluída' })[status] || status || '—';
  }
  function statusClass(status) {
    return ({ PENDING_APPROVAL:'pending', APPROVED:'approved', REJECTED:'rejected', CANCELLED:'cancelled', EXPIRED:'expired', ACTIVE:'active', PROVISIONING:'provisioning', REVOKING:'provisioning', REVOKED:'revoked', FAILED:'failed', CLOSED:'closed' })[status] || 'closed';
  }
  function accessLabel(profile) {
    return ({ READ_ONLY:'Somente leitura', DIAGNOSTIC:'Diagnóstico', MAINTENANCE:'Manutenção' })[profile] || profile || '—';
  }
  function assetTypeLabel(type) {
    return ({ ENGINEERING_STATION:'Estação de engenharia', SCADA_SERVER:'Servidor SCADA', HMI:'IHM', PLC:'CLP' })[type] || type || '—';
  }
  function criticalityClass(level) {
    return ({ CRITICAL:'critical', HIGH:'high', MEDIUM:'medium', LOW:'' })[level] || '';
  }
  function dateTime(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat('pt-BR', { dateStyle:'short', timeStyle:'short' }).format(d);
  }
  function dateOnly(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat('pt-BR', { dateStyle:'medium' }).format(d);
  }
  function shortId(value) { return value ? `${String(value).slice(0, 8)}…` : '—'; }
  function toast(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast ${type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
    el.textContent = message;
    toastRegion.appendChild(el);
    window.setTimeout(() => el.remove(), 4600);
  }
  function showError(error, prefix = 'Não foi possível concluir a operação.') {
    const detail = error?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || error?.message || prefix;
    toast(message, 'error');
  }
  function saveAuth() {
    if (!state.token || !state.user) return;
    sessionStorage.setItem(AUTH_KEY, JSON.stringify({ token:state.token, user:state.user, mfaVerifiedAt:state.mfaVerifiedAt }));
  }
  function clearAuth() {
    state.token = null; state.user = null; state.mfaVerifiedAt = null;
    state.challengeToken = null; state.challengeMode = null; state.pendingAuthorization = null;
    sessionStorage.removeItem(AUTH_KEY);
  }
  function saveSessions() { sessionStorage.setItem(SESSIONS_KEY, JSON.stringify(state.sessions.slice(0, 30))); }

  async function api(path, options = {}) {
    if (state.preview) throw new Error('Modo de pré-visualização: chamadas à API estão desativadas.');
    const headers = { 'Accept':'application/json', ...(options.headers || {}) };
    if (options.body !== undefined && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const bearer = options.tokenOverride !== undefined ? options.tokenOverride : state.token;
    if (bearer) headers.Authorization = `Bearer ${bearer}`;
    const init = { method:options.method || 'GET', headers, body:options.body === undefined ? undefined : JSON.stringify(options.body) };
    let response;
    try { response = await fetch(`/api${path}`, init); }
    catch (e) { state.online = false; throw new Error('Não foi possível alcançar a API. Confirme se o backend FastAPI está iniciado em 127.0.0.1:8000.'); }
    const raw = await response.text();
    let payload = null;
    try { payload = raw ? JSON.parse(raw) : null; } catch { payload = { detail: raw || response.statusText }; }
    if (!response.ok) {
      const err = new Error(typeof payload?.detail === 'string' ? payload.detail : payload?.detail?.message || `Falha HTTP ${response.status}`);
      err.status = response.status; err.detail = payload?.detail; err.payload = payload;
      throw err;
    }
    state.online = true;
    return payload;
  }

  function shellBrand() {
    return `<div class="brand-lockup"><img class="brand-mark" src="./assets/logo_validaot_simbolo.webp" alt="Símbolo ValidaOT" width="56" height="42" /><div><div class="brand-name">ValidaOT</div><div class="brand-sub">Segurança e Controle Industrial</div></div></div>`;
  }

  function renderLogin(errorMessage = '') {
    app.innerHTML = `
      <main class="auth-page">
        <aside class="auth-aside">
          ${shellBrand()}
          <div class="aside-copy">
            <div class="eyebrow">Cibersegurança em redes industriais</div>
            <h1>O acesso certo.<br>Com a validação certa.</h1>
            <p>Uma camada de governança para solicitações de terceiros, ordens de serviço e acessos temporários a ativos de Tecnologia Operacional.</p>
            <div class="aside-tags"><span>MFA obrigatório</span><span>Privilégio mínimo</span><span>Trilha de auditoria</span></div>
          </div>
          <div class="aside-foot">AMBIENTE DE DEMONSTRAÇÃO · ADAPTADOR SIMULADO</div>
        </aside>
        <section class="auth-main">
          <div class="auth-card">
            ${shellBrand()}
            <div class="auth-kicker">Acesso à plataforma</div>
            <h2>Entre na sua conta</h2>
            <p class="auth-lead">Utilize as credenciais cadastradas no ambiente ValidaOT para continuar.</p>
            ${errorMessage ? `<div class="alert alert-error">${esc(errorMessage)}</div>` : ''}
            <form id="login-form">
              <div class="field"><label for="login-email">E-mail corporativo</label><input id="login-email" name="email" type="email" autocomplete="username" placeholder="nome@empresa.com" required /></div>
              <div class="field"><label for="login-password">Senha</label><input id="login-password" name="password" type="password" autocomplete="current-password" placeholder="Digite sua senha" required /></div>
              <button class="btn btn-primary btn-block" type="submit">Entrar na ValidaOT <span aria-hidden="true">→</span></button>
            </form>
            <div class="auth-note">O acesso de técnicos terceirizados exige autenticação multifator (MFA). A plataforma não se conecta diretamente a CLPs, SCADA ou equipamentos industriais reais neste ambiente demonstrativo.</div>
            <section class="preview-entry" aria-label="Pré-visualização visual">
              <div class="preview-entry-title">Quer explorar as telas sem autenticar?</div>
              <p>Abra uma prévia local com dados fictícios. Nenhuma ação será enviada ao backend.</p>
              <div class="preview-role-grid">
                <button type="button" class="btn btn-outline" data-preview-role="TECHNICIAN">Técnico</button>
                <button type="button" class="btn btn-outline" data-preview-role="APPROVER">Aprovador</button>
                <button type="button" class="btn btn-outline" data-preview-role="OT_ADMIN">Administrador OT</button>
                <button type="button" class="btn btn-outline" data-preview-role="AUDITOR">Auditor</button>
              </div>
            </section>
          </div>
        </section>
      </main>`;
  }

  function renderMfa(mode, data = {}, errorMessage = '') {
    const setup = mode === 'setup';
    const title = setup ? 'Ative a autenticação MFA' : 'Confirme sua identidade';
    const lead = setup ? 'Escaneie o QR Code com um aplicativo autenticador (TOTP), como Microsoft Authenticator, Google Authenticator ou outro compatível. Depois informe o código de seis dígitos.' : 'Abra seu aplicativo autenticador e informe o código TOTP atual para concluir o login.';
    app.innerHTML = `
      <main class="auth-page"><aside class="auth-aside">${shellBrand()}<div class="aside-copy"><div class="eyebrow">Verificação em duas etapas</div><h1>Mais uma camada de proteção para o acesso OT.</h1><p>O segundo fator ajuda a confirmar a identidade do técnico antes que uma solicitação possa avançar para a liberação.</p><div class="aside-tags"><span>Código de 6 dígitos</span><span>Uso único</span><span>Tempo limitado</span></div></div><div class="aside-foot">ValidaOT · AUTENTICAÇÃO MULTIFATOR</div></aside>
        <section class="auth-main"><div class="auth-card">${shellBrand()}<div class="auth-kicker">Autenticação multifator</div><h2>${title}</h2><p class="auth-lead">${lead}</p>
          ${errorMessage ? `<div class="alert alert-error">${esc(errorMessage)}</div>` : ''}
          ${setup && data.qr_code_data_uri ? `<div class="qr-wrap"><img src="${esc(data.qr_code_data_uri)}" alt="QR Code para configurar MFA" /></div><div class="alert alert-warning">Não compartilhe este QR Code nem a chave de configuração. Ela permite gerar códigos de autenticação da sua conta.</div>` : ''}
          ${setup && data.provisioning_uri ? `<details class="field-hint" style="margin:0 0 16px"><summary>Não consegue escanear o QR Code?</summary><div class="mono" style="overflow-wrap:anywhere;margin-top:8px">${esc(data.provisioning_uri)}</div></details>` : ''}
          <form id="mfa-form"><div class="field"><label for="mfa-code">Código de autenticação</label><input id="mfa-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="000000" required /></div><button type="submit" class="btn btn-primary btn-block">${setup ? 'Confirmar e ativar MFA' : 'Verificar e entrar'} <span aria-hidden="true">→</span></button></form>
          <div class="auth-note">${setup ? 'Após confirmar o código, sua conta será ativada com MFA.' : 'O código é temporário e não deve ser compartilhado.'} <button class="link-btn" id="cancel-auth">Voltar ao login</button></div>
        </div></section></main>`;
    $('#cancel-auth')?.addEventListener('click', () => { clearAuth(); renderLogin(); });
  }

  const PREVIEW_FIXTURES = {
    assets: [
      { id:'preview-asset-eng', asset_code:'ENG-01', name:'Estação de Engenharia 01', asset_type:'ENGINEERING_STATION', criticality:'HIGH', status:'ACTIVE' },
      { id:'preview-asset-plc', asset_code:'PLC-01', name:'CLP da Linha de Embalagem', asset_type:'PLC', criticality:'CRITICAL', status:'ACTIVE' },
      { id:'preview-asset-scada', asset_code:'SCADA-01', name:'Servidor SCADA 01', asset_type:'SCADA_SERVER', criticality:'HIGH', status:'ACTIVE' },
      { id:'preview-asset-hmi', asset_code:'HMI-01', name:'IHM da Linha 01', asset_type:'HMI', criticality:'MEDIUM', status:'ACTIVE' },
    ],
    orders: [
      { id:'preview-order-001', code:'OS-DEMO-001', description:'Diagnóstico na estação de engenharia', asset_id:'preview-asset-eng', is_critical:false, status:'OPEN', planned_start_at:'2026-11-02T08:00:00-03:00', planned_end_at:'2026-11-02T18:00:00-03:00' },
      { id:'preview-order-002', code:'OS-DEMO-002', description:'Manutenção programada do CLP crítico', asset_id:'preview-asset-plc', is_critical:false, status:'IN_PROGRESS', planned_start_at:'2026-11-02T09:00:00-03:00', planned_end_at:'2026-11-02T17:00:00-03:00' },
      { id:'preview-order-003', code:'OS-DEMO-003', description:'Intervenção crítica no servidor SCADA', asset_id:'preview-asset-scada', is_critical:true, status:'OPEN', planned_start_at:'2026-11-02T10:00:00-03:00', planned_end_at:'2026-11-02T16:00:00-03:00' },
    ],
    requests: [
      { id:'preview-request-001', request_code:'REQ-DEMO-0142', requester_id:'preview-tech', work_order_id:'preview-order-001', asset_id:'preview-asset-eng', access_profile:'DIAGNOSTIC', rationale:'Diagnóstico de comunicação após manutenção programada.', status:'PENDING_APPROVAL', requires_dual_approval:false, required_approvals:1, approved_count:0, requested_start_at:'2026-11-02T13:00:00-03:00', requested_end_at:'2026-11-02T14:30:00-03:00' },
      { id:'preview-request-002', request_code:'REQ-DEMO-0143', requester_id:'preview-tech', work_order_id:'preview-order-002', asset_id:'preview-asset-plc', access_profile:'MAINTENANCE', rationale:'Intervenção controlada no CLP da linha de embalagem.', status:'PENDING_APPROVAL', requires_dual_approval:true, required_approvals:2, approved_count:1, criticality_reason:'Ativo crítico', requested_start_at:'2026-11-02T14:00:00-03:00', requested_end_at:'2026-11-02T15:00:00-03:00' },
      { id:'preview-request-003', request_code:'REQ-DEMO-0138', requester_id:'preview-tech', work_order_id:'preview-order-003', asset_id:'preview-asset-scada', access_profile:'READ_ONLY', rationale:'Verificação de alarmes e diagnóstico inicial.', status:'APPROVED', requires_dual_approval:true, required_approvals:2, approved_count:2, criticality_reason:'Ordem de serviço crítica', requested_start_at:'2026-11-02T11:00:00-03:00', requested_end_at:'2026-11-02T12:00:00-03:00' },
      { id:'preview-request-004', request_code:'REQ-DEMO-0131', requester_id:'preview-tech', work_order_id:'preview-order-001', asset_id:'preview-asset-eng', access_profile:'READ_ONLY', rationale:'Consulta técnica encerrada para demonstração.', status:'REJECTED', requires_dual_approval:false, required_approvals:1, approved_count:0, requested_start_at:'2026-11-01T13:00:00-03:00', requested_end_at:'2026-11-01T14:00:00-03:00' },
    ],
    events: [
      { id:'preview-event-001', actor_user_id:'preview-tech', actor_email:'tecnico@validaot.com', event_type:'ACCESS_REQUEST_SUBMITTED', entity_type:'ACCESS_REQUEST', entity_id:'preview-request-002', occurred_at:'2026-11-02T12:05:00-03:00', outcome:'SUCCESS', correlation_id:'preview-corr-001', details:{ request_code:'REQ-DEMO-0143', access_profile:'MAINTENANCE' } },
      { id:'preview-event-002', actor_user_id:'preview-approver-1', actor_email:'aprovador1@validaot.com', event_type:'ACCESS_REQUEST_DECISION', entity_type:'ACCESS_REQUEST', entity_id:'preview-request-002', occurred_at:'2026-11-02T12:10:00-03:00', outcome:'SUCCESS', correlation_id:'preview-corr-002', details:{ decision:'APPROVED', approved_count:1, required_approvals:2 } },
      { id:'preview-event-003', actor_user_id:'preview-tech', actor_email:'tecnico@validaot.com', event_type:'MFA_VERIFIED', entity_type:'USER', entity_id:'preview-tech', occurred_at:'2026-11-02T11:55:00-03:00', outcome:'SUCCESS', correlation_id:'preview-corr-003', details:{ method:'TOTP' } },
      { id:'preview-event-004', actor_user_id:'preview-admin', actor_email:'admin@validaot.com', event_type:'SESSION_REVOKED_SIMULATED', entity_type:'ACCESS_SESSION', entity_id:'preview-session-001', occurred_at:'2026-11-02T10:30:00-03:00', outcome:'SUCCESS', correlation_id:'preview-corr-004', details:{ adapter:'SIMULATED' } },
      { id:'preview-event-005', actor_user_id:'preview-auditor', actor_email:'auditor@validaot.com', event_type:'SESSION_REVOKE_DENIED', entity_type:'ACCESS_SESSION', entity_id:'preview-session-002', occurred_at:'2026-11-02T10:15:00-03:00', outcome:'DENIED', correlation_id:'preview-corr-005', details:{ reason:'ROLE_NOT_ALLOWED', role:'AUDITOR' } },
    ],
    sessions: [
      { sessionId:'SIM-SESSION-DEMO-001', requestId:'preview-request-003', requestCode:'REQ-DEMO-0138', status:'ACTIVE', adapter:'SIMULATED', createdAt:'2026-11-02T11:05:00-03:00', checkedAt:'2026-11-02T11:10:00-03:00' },
      { sessionId:'SIM-SESSION-DEMO-002', requestId:'preview-request-002', requestCode:'REQ-DEMO-0143', status:'REVOKED', adapter:'SIMULATED', createdAt:'2026-11-01T15:00:00-03:00', checkedAt:'2026-11-01T16:00:00-03:00' },
    ],
  };

  function enterPreview(role) {
    const people = {
      TECHNICIAN: { id:'preview-tech', full_name:'Técnico de Demonstração', email:'tecnico@validaot.com', role:'TECHNICIAN' },
      APPROVER: { id:'preview-approver-1', full_name:'Aprovador de Demonstração', email:'aprovador1@validaot.com', role:'APPROVER' },
      OT_ADMIN: { id:'preview-admin', full_name:'Administrador de Demonstração', email:'admin@validaot.com', role:'OT_ADMIN' },
      AUDITOR: { id:'preview-auditor', full_name:'Auditor de Demonstração', email:'auditor@validaot.com', role:'AUDITOR' },
    };
    if (!people[role]) return;
    if (state.realSessionsBeforePreview === null) state.realSessionsBeforePreview = state.sessions;
    state.preview = true;
    state.token = null;
    state.challengeToken = null;
    state.challengeMode = null;
    state.user = { ...people[role] };
    state.view = 'dashboard';
    state.online = false;
    state.data = {
      assets: PREVIEW_FIXTURES.assets.map(x => ({...x})),
      orders: PREVIEW_FIXTURES.orders.map(x => ({...x})),
      requests: PREVIEW_FIXTURES.requests.filter(r => role !== 'APPROVER' || r.status === 'PENDING_APPROVAL').map(x => ({...x})),
      events: PREVIEW_FIXTURES.events.map(x => ({...x, details:{...x.details}})),
      sessions: [],
      sessionsTotal: 0,
      sessionsActiveTotal: PREVIEW_FIXTURES.sessions.filter(s => s.status === 'ACTIVE').length,
      auditTotal: PREVIEW_FIXTURES.events.length,
    };
    state.sessions = PREVIEW_FIXTURES.sessions.map(x => ({...x}));
    renderShell();
    toast(`Pré-visualização aberta como ${roleLabel(role)}. Dados fictícios; operações desativadas.`);
  }

  function exitPreview() {
    state.preview = false;
    if (state.realSessionsBeforePreview !== null) {
      state.sessions = state.realSessionsBeforePreview;
      state.realSessionsBeforePreview = null;
    }
    state.user = null;
    state.token = null;
    state.data = { assets:[], orders:[], requests:[], events:[], sessions:[], sessionsTotal:0, sessionsActiveTotal:0 };
    state.view = 'dashboard';
    renderLogin();
  }

  const navItems = [
    { id:'dashboard', label:'Visão geral', icon:'◫', group:'GESTÃO' },
    { id:'requests', label:'Solicitações', icon:'▤', group:'GESTÃO', roles:['TECHNICIAN','OT_ADMIN','AUDITOR'] },
    { id:'approvals', label:'Aprovações', icon:'✓', group:'GESTÃO', roles:['APPROVER'] },
    { id:'operations', label:'Ordens e ativos', icon:'▦', group:'AMBIENTE' },
    { id:'sessions', label:'Sessões de acesso', icon:'◉', group:'AMBIENTE' },
    { id:'audit', label:'Auditoria', icon:'⌁', group:'SEGURANÇA', roles:['OT_ADMIN','AUDITOR'] },
  ];
  function visibleNav() { return navItems.filter(item => !item.roles || item.roles.includes(state.user?.role)); }
  function pageTitle() { return (navItems.find(x => x.id === state.view)?.label || 'Visão geral'); }

  function renderShell() {
    const nav = visibleNav();
    let lastGroup = '';
    const navHtml = nav.map(item => {
      const group = item.group !== lastGroup ? `<div class="nav-group-label">${item.group}</div>` : '';
      lastGroup = item.group;
      return `${group}<button class="nav-item ${state.view === item.id ? 'active' : ''}" data-nav="${item.id}"><span class="nav-icon">${item.icon}</span>${item.label}</button>`;
    }).join('');
    app.innerHTML = `
      <div class="app-shell">
        <div class="mobile-nav-overlay ${state.mobileNavOpen ? 'show' : ''}" id="mobile-overlay"></div>
        <aside class="sidebar ${state.mobileNavOpen ? 'open' : ''}" id="sidebar">
          ${shellBrand()}
          <nav class="nav-list">${navHtml}</nav>
          <div class="sidebar-bottom"><div class="env-card"><strong><span class="dot online" style="margin-right:7px"></span>Ambiente controlado</strong><span>Adaptador SIMULATED<br>Sem conexão com rede industrial real</span></div></div>
        </aside>
        <main class="main-area">
          ${state.preview ? `<div class="preview-banner"><strong>PRÉ-VISUALIZAÇÃO LOCAL</strong><span>Dados fictícios · Nenhuma chamada será enviada à API · Ações de gravação desativadas</span><button type="button" class="mini-action" id="switch-preview-role">Trocar perfil</button></div>` : ''}
          <header class="topbar">
            <div style="display:flex;align-items:center;gap:12px"><button class="mobile-menu" id="mobile-menu" aria-label="Abrir menu">☰</button><div><div class="topbar-title">${pageTitle()}</div><div class="topbar-context">Controle de acesso e governança de terceiros · OT</div></div></div>
            <div class="topbar-right"><div class="connection"><span class="dot ${state.preview ? 'preview' : state.online ? 'online' : 'offline'}"></span>${state.preview ? 'Prévia local' : state.online ? 'API conectada' : 'API não verificada'}</div><div class="user-menu"><div class="avatar">${esc(initials(state.user?.full_name))}</div><div class="user-meta"><strong>${esc(state.user?.full_name)}</strong><span>${esc(roleLabel(state.user?.role))}</span></div><button class="mini-action" id="logout-btn">${state.preview ? 'Sair da prévia' : 'Sair'}</button></div></div>
          </header>
          <section class="content" id="page-content">${renderCurrentView()}</section>
        </main>
      </div>`;
  }

  function statCard(label, value, note, icon, color = '#168e83', bg = '#e9f7f4') {
    return `<div class="card stat-card" style="--stat-color:${color};--stat-bg:${bg}"><div class="stat-top"><span class="stat-label">${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></div>`;
  }
  function requestOrder(request) { return state.data.orders.find(o => o.id === request.work_order_id); }
  function requestAsset(request) { return state.data.assets.find(a => a.id === request.asset_id); }
  function emptyState(title, text, icon = '✓') { return `<div class="empty-state"><div class="empty-icon">${icon}</div><strong>${title}</strong><p>${text}</p></div>`; }
  function requestRow(r, withActions = false) {
    const order = requestOrder(r); const asset = requestAsset(r);
    const critical = r.requires_dual_approval;
    return `<tr>
      <td><strong>${esc(r.request_code || shortId(r.id))}</strong><span class="table-secondary">${esc(shortId(r.id))}</span></td>
      <td><span class="table-primary">${esc(order?.code || shortId(r.work_order_id))}</span><span class="table-secondary">${esc(asset?.asset_code || asset?.name || shortId(r.asset_id))}</span></td>
      <td>${esc(accessLabel(r.access_profile))}</td>
      <td><span class="status ${statusClass(r.status)}">${esc(statusLabel(r.status))}</span></td>
      <td>${critical ? '<span class="badge critical">2 aprovações</span>' : '<span class="badge">1 aprovação</span>'}</td>
      ${withActions ? `<td><button class="mini-action" data-action="view-request" data-id="${esc(r.id)}">Detalhes</button></td>` : ''}
    </tr>`;
  }

  function renderDashboard() {
    const role = state.user.role;
    const requests = state.data.requests;
    const pending = requests.filter(r => r.status === 'PENDING_APPROVAL').length;
    const approved = requests.filter(r => r.status === 'APPROVED').length;
    const activeSessions = state.preview ? state.sessions.filter(s => s.status === 'ACTIVE').length : state.data.sessionsActiveTotal;
    const isTech = role === 'TECHNICIAN';
    const isApprover = role === 'APPROVER';
    const isAudit = ['OT_ADMIN','AUDITOR'].includes(role);
    const primary = isTech ? 'Acompanhe suas solicitações e inicie acessos aprovados dentro da janela autorizada.' : isApprover ? 'Revise solicitações pendentes e registre decisões de acordo com a criticidade.' : isAudit ? 'Acompanhe os registros do ambiente e os indicadores de controle de acesso.' : 'Acompanhe a operação de acesso de terceiros e as solicitações registradas.';
    let stats = '';
    if (isTech) stats = statCard('Minhas solicitações', requests.length, 'Pedidos associados à sua conta', '▤') + statCard('Aguardando aprovação', pending, 'Solicitações pendentes', '◷', '#ac7b28', '#fff5e5') + statCard('Aprovadas', approved, 'Prontas para seguir o fluxo', '✓', '#21845f', '#e8f7f0') + statCard('Sessões ativas', activeSessions, state.preview ? 'Sessões fictícias da pré-visualização' : 'Sessões ativas registradas no backend', '◉', '#5275a0', '#edf3fb');
    else if (isApprover) stats = statCard('Pendentes', pending, 'Solicitações aguardando decisão', '◷', '#ac7b28', '#fff5e5') + statCard('Ativos cadastrados', state.data.assets.length, 'Ativos OT disponíveis para consulta', '▦') + statCard('Ordens de serviço', state.data.orders.length, 'Ordens visíveis ao seu perfil', '▤', '#5275a0', '#edf3fb');
    else stats = statCard('Solicitações visíveis', requests.length, 'Registros retornados pela API', '▤') + statCard('Pendentes', pending, 'Aguardando decisão', '◷', '#ac7b28', '#fff5e5') + statCard('Ativos OT', state.data.assets.length, 'Ativos cadastrados', '▦', '#5275a0', '#edf3fb') + statCard('Eventos carregados', state.data.events.length, 'Eventos da trilha de auditoria', '⌁', '#6b6b9f', '#f0effa');
    const recent = requests.slice(0, 5);
    const recentHtml = recent.length ? `<div class="table-wrap"><table><thead><tr><th>Solicitação</th><th>Ordem / ativo</th><th>Perfil</th><th>Status</th><th>Quórum</th></tr></thead><tbody>${recent.map(r => requestRow(r)).join('')}</tbody></table></div>` : emptyState('Nenhuma solicitação encontrada','Quando houver solicitações para o seu perfil, elas aparecerão aqui.','▤');
    const shortcuts = isTech ? `<button class="btn btn-primary" data-action="new-request">＋ Nova solicitação</button><button class="btn btn-outline" data-nav="operations">Consultar ativos</button>` : isApprover ? `<button class="btn btn-primary" data-nav="approvals">Abrir fila de aprovações</button>` : `<button class="btn btn-outline" data-nav="audit">Consultar auditoria</button><button class="btn btn-outline" data-nav="operations">Ver ativos e ordens</button>`;
    return `<div class="page-heading"><div><h1>Olá, ${esc((state.user.full_name || '').split(' ')[0] || 'usuário')}.</h1><p>${primary}</p></div><div class="heading-actions">${shortcuts}</div></div>
      <div class="grid grid-4" style="margin-bottom:17px">${stats}</div>
      <div class="two-column">
        <div class="card"><div class="card-pad"><div class="section-head"><div><h3>Solicitações recentes</h3><div class="sub">Visão atual retornada pelo backend</div></div><button class="link-btn" data-nav="${isApprover ? 'approvals' : 'requests'}">Ver todas →</button></div></div>${recentHtml}</div>
        <div class="card card-pad"><div class="section-head"><div><h3>Controles do ambiente</h3><div class="sub">Premissas ativas da demonstração</div></div><span class="badge">SIMULATED</span></div>
          <div class="profile-row"><div class="profile-icon">◈</div><div><strong>MFA para técnicos</strong><small>Segundo fator TOTP no fluxo de acesso</small></div><span class="status active" style="margin-left:auto">Ativo</span></div>
          <div class="profile-row"><div class="profile-icon">Ⅱ</div><div><strong>Aprovação por criticidade</strong><small>Ativo crítico OU OS crítica exige 2 aprovadores</small></div><span class="status active" style="margin-left:auto">Ativo</span></div>
          <div class="profile-row"><div class="profile-icon">⌁</div><div><strong>Rastreabilidade</strong><small>Eventos relevantes registrados no backend</small></div><span class="status active" style="margin-left:auto">Ativo</span></div>
          <div class="info-strip" style="margin-top:14px">A interface organiza as decisões de autorização. A abertura de conexão técnica com equipamentos industriais não é realizada pelo MVP.</div>
        </div>
      </div>`;
  }

  function renderRequests() {
    const isTech = state.user.role === 'TECHNICIAN';
    const list = state.data.requests;
    return `<div class="page-heading"><div><h1>Solicitações de acesso</h1><p>${isTech ? 'Crie pedidos vinculados a uma ordem de serviço e acompanhe o andamento das aprovações.' : 'Consulte os pedidos de acesso retornados pelo backend para o seu perfil.'}</p></div><div class="heading-actions">${isTech ? '<button class="btn btn-primary" data-action="new-request">＋ Nova solicitação</button>' : ''}<button class="btn btn-outline" data-action="reload">↻ Atualizar</button></div></div>
      <div class="card"><div class="card-pad"><div class="toolbar"><input class="search" id="request-search" placeholder="Buscar por código, ativo ou ordem de serviço" /><select id="request-status"><option value="">Todos os status</option><option value="PENDING_APPROVAL">Aguardando aprovação</option><option value="APPROVED">Aprovada</option><option value="REJECTED">Recusada</option><option value="CANCELLED">Cancelada</option><option value="EXPIRED">Expirada</option></select></div></div><div id="request-table">${renderRequestTable(list)}</div></div>`;
  }
  function renderRequestTable(list) {
    if (!list.length) return emptyState('Nenhuma solicitação encontrada','A lista ficará disponível após a criação de pedidos ou quando houver registros para o seu perfil.','▤');
    return `<div class="table-wrap"><table><thead><tr><th>Código</th><th>Ordem / ativo</th><th>Perfil de acesso</th><th>Status</th><th>Aprovação</th><th></th></tr></thead><tbody>${list.map(r => `<tr>${requestRow(r).replace(/^<tr>/,'').replace('</tr>','')}<td><button class="mini-action" data-action="view-request" data-id="${esc(r.id)}">Detalhes</button>${isEligibleToAuthorize(r) ? ` <button class="mini-action" data-action="authorize" data-id="${esc(r.id)}">Autorizar</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function isEligibleToAuthorize(r) { return state.user.role === 'TECHNICIAN' && r.status === 'APPROVED'; }

  function renderApprovals() {
    const items = state.data.requests.filter(r => r.status === 'PENDING_APPROVAL');
    return `<div class="page-heading"><div><h1>Fila de aprovações</h1><p>Analise a ordem, o ativo, a finalidade e a criticidade antes de registrar sua decisão.</p></div><button class="btn btn-outline" data-action="reload">↻ Atualizar fila</button></div>
      <div class="info-strip" style="margin-bottom:15px"><strong>Regra de quórum:</strong> solicitações relacionadas a ativo crítico <em>ou</em> ordem de serviço crítica exigem duas aprovações de pessoas distintas. Nos demais casos, uma aprovação é suficiente.</div>
      ${items.length ? `<div class="request-cards">${items.map(r => { const order=requestOrder(r), asset=requestAsset(r); return `<article class="card request-card"><div><div style="display:flex;gap:9px;align-items:center;flex-wrap:wrap"><h3>${esc(r.request_code || shortId(r.id))}</h3><span class="status pending">Pendente</span>${r.requires_dual_approval?'<span class="badge critical">Quórum duplo</span>':''}</div><div class="meta">OS ${esc(order?.code || shortId(r.work_order_id))} · ${esc(asset?.asset_code || asset?.name || 'Ativo não identificado')}</div><div class="request-facts"><span>Ativo: <b>${esc(asset?.name || '—')}</b></span><span>Tipo: <b>${esc(assetTypeLabel(asset?.asset_type))}</b></span><span>Perfil: <b>${esc(accessLabel(r.access_profile))}</b></span><span>Janela: <b>${esc(dateTime(r.requested_start_at))} – ${esc(dateTime(r.requested_end_at))}</b></span></div><div class="request-facts"><span>Motivo: <b>${esc(r.rationale || 'Não informado')}</b></span></div></div><div class="request-actions"><button class="btn btn-outline btn-sm" data-action="view-request" data-id="${esc(r.id)}">Detalhes</button><button class="btn btn-danger btn-sm" data-action="decision" data-id="${esc(r.id)}" data-decision="REJECTED">Recusar</button><button class="btn btn-success btn-sm" data-action="decision" data-id="${esc(r.id)}" data-decision="APPROVED">Aprovar</button></div></article>`; }).join('')}</div>` : emptyState('Fila sem solicitações pendentes','Não há pedidos aguardando decisão no momento.','✓')}`;
  }

  function renderOperations() {
    return `<div class="page-heading"><div><h1>Ordens de serviço e ativos</h1><p>Consulte os dados operacionais utilizados como contexto das solicitações de acesso.</p></div><button class="btn btn-outline" data-action="reload">↻ Atualizar dados</button></div>
      <div class="grid grid-2">
        <div class="card"><div class="card-pad"><div class="section-head"><div><h3>Ativos OT</h3><div class="sub">Estações, servidores SCADA, IHMs e CLPs</div></div><span class="badge">${state.data.assets.length} registros</span></div></div>${state.data.assets.length ? `<div class="table-wrap"><table><thead><tr><th>Ativo</th><th>Tipo</th><th>Criticidade</th><th>Status</th></tr></thead><tbody>${state.data.assets.map(a => `<tr><td><strong>${esc(a.asset_code)}</strong><span class="table-secondary">${esc(a.name)}</span></td><td>${esc(assetTypeLabel(a.asset_type))}</td><td><span class="badge ${criticalityClass(a.criticality)}">${esc(a.criticality)}</span></td><td><span class="status ${a.status==='ACTIVE'?'active':'closed'}">${esc(statusLabel(a.status))}</span></td></tr>`).join('')}</tbody></table></div>` : emptyState('Nenhum ativo retornado','Verifique a conexão com a API.','▦')}</div>
        <div class="card"><div class="card-pad"><div class="section-head"><div><h3>Ordens de serviço</h3><div class="sub">Janelas e responsáveis da intervenção</div></div><span class="badge">${state.data.orders.length} registros</span></div></div>${state.data.orders.length ? `<div class="table-wrap"><table><thead><tr><th>Ordem</th><th>Janela</th><th>Criticidade</th><th>Status</th></tr></thead><tbody>${state.data.orders.map(o => {const a=state.data.assets.find(x=>x.id===o.asset_id); return `<tr><td><strong>${esc(o.code)}</strong><span class="table-secondary">${esc(a?.asset_code || shortId(o.asset_id))}</span></td><td>${esc(dateTime(o.planned_start_at))}<span class="table-secondary">até ${esc(dateTime(o.planned_end_at))}</span></td><td>${o.is_critical?'<span class="badge critical">Crítica</span>':'<span class="badge">Normal</span>'}</td><td><span class="status ${o.status==='OPEN'?'active':'closed'}">${esc(statusLabel(o.status))}</span></td></tr>`; }).join('')}</tbody></table></div>` : emptyState('Nenhuma ordem retornada','A lista depende dos registros disponíveis para o seu perfil.','▤')}</div>
      </div>`;
  }

  function renderSessions() {
    const sessions = state.preview ? state.sessions : state.data.sessions;

    if (state.preview) {
      return `<div class="page-heading"><div><h1>Sessões de acesso</h1><p>Consulte as sessões fictícias da pré-visualização do ValidaOT.</p></div></div>
        <div class="warning-strip" style="margin-bottom:15px"><strong>Pré-visualização:</strong> os registros abaixo são fictícios. Consultas e revogações reais estão desativadas.</div>
        <div class="card card-pad" style="margin-bottom:15px"><div class="section-head"><div><h3>Consultar sessão por identificador</h3><div class="sub">Informe o ID externo de uma sessão de demonstração</div></div></div><form id="session-lookup" class="toolbar"><input class="search" id="session-id-input" placeholder="Ex.: SIM-SESSION-000001" required /><button class="btn btn-primary" type="submit">Consultar sessão</button></form></div>
        <div class="card"><div class="card-pad"><div class="section-head"><div><h3>Sessões de demonstração</h3><div class="sub">Registros fictícios para apresentação</div></div></div></div>
        ${sessions.length ? `<div class="table-wrap"><table><thead><tr><th>Sessão</th><th>Solicitação</th><th>Status</th><th>Última consulta</th><th>Ações</th></tr></thead><tbody>${sessions.map(s => `<tr><td><strong class="mono">${esc(s.sessionId)}</strong><span class="table-secondary">${esc(s.adapter || 'SIMULATED')}</span></td><td>${esc(s.requestCode || shortId(s.requestId))}</td><td><span class="status ${statusClass(s.status)}">${esc(statusLabel(s.status))}</span></td><td>${esc(dateTime(s.checkedAt || s.createdAt))}</td><td><button class="mini-action" data-action="inspect-session" data-id="${esc(s.sessionId)}">Consultar</button>${canRevoke(s) ? ` <button class="mini-action" data-action="revoke-session" data-id="${esc(s.sessionId)}">Revogar</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : emptyState('Nenhuma sessão de demonstração','Os exemplos de sessões estão disponíveis para visualização.','◉')}</div>`;
    }

    const total = Number.isFinite(state.data.sessionsTotal) ? state.data.sessionsTotal : sessions.length;

    return `<div class="page-heading"><div><h1>Sessões de acesso</h1><p>Consulte as sessões persistidas pelo backend e acompanhe os acessos de terceiros ao ambiente industrial.</p></div></div>
      <div class="card card-pad" style="margin-bottom:15px"><div class="section-head"><div><h3>Consultar sessão por identificador</h3><div class="sub">Informe o identificador externo retornado pelo adaptador</div></div></div><form id="session-lookup" class="toolbar"><input class="search" id="session-id-input" placeholder="Ex.: SIM-SESSION-000001" required /><button class="btn btn-primary" type="submit">Consultar sessão</button></form></div>
      ${total > sessions.length ? `<div class="warning-strip" style="margin-bottom:15px">Exibindo ${sessions.length} de ${total} sessões visíveis para o seu perfil. A navegação entre páginas será disponibilizada em uma próxima atualização.</div>` : ''}
      <div class="card"><div class="card-pad"><div class="section-head"><div><h3>Sessões registradas</h3><div class="sub">Exibindo ${sessions.length} de ${total} sessões visíveis para o seu perfil</div></div></div></div>
      ${sessions.length ? `<div class="table-wrap"><table><thead><tr><th>Sessão</th><th>Solicitação</th><th>Técnico</th><th>Ativo OT</th><th>Perfil</th><th>Status</th><th>Validade</th><th>Ações</th></tr></thead><tbody>${sessions.map(s => {
        const sessionId = s.session_id || s.external_session_id || '';
        const assetCode = s.asset_code || shortId(s.asset_id);
        const approvalSummary = Number.isFinite(s.approved_count) && Number.isFinite(s.required_approvals) ? `${s.approved_count}/${s.required_approvals} aprovações` : '';
        return `<tr>
          <td><strong class="mono">${esc(sessionId || '—')}</strong><span class="table-secondary">${esc(s.adapter || 'SIMULATED')}</span></td>
          <td>${esc(s.request_code || shortId(s.access_request_id))}${approvalSummary ? `<span class="table-secondary">${esc(approvalSummary)}</span>` : ''}</td>
          <td>${esc(s.requester_name || shortId(s.requester_id))}</td>
          <td><strong>${esc(assetCode)}</strong>${s.asset_name ? `<span class="table-secondary">${esc(s.asset_name)}</span>` : ''}${s.asset_type ? `<span class="table-secondary">${esc(assetTypeLabel(s.asset_type))}</span>` : ''}</td>
          <td>${esc(accessLabel(s.access_profile))}</td>
          <td><span class="status ${statusClass(s.status)}">${esc(statusLabel(s.status))}</span></td>
          <td><span>${esc(dateTime(s.valid_from))}</span><span class="table-secondary">Até ${esc(dateTime(s.expires_at))}</span>${s.started_at ? `<span class="table-secondary">Iniciada: ${esc(dateTime(s.started_at))}</span>` : ''}${s.closed_at ? `<span class="table-secondary">Encerrada: ${esc(dateTime(s.closed_at))}</span>` : ''}</td>
          <td><button class="mini-action" data-action="inspect-session" data-id="${esc(sessionId)}">Consultar</button>${canRevoke(s) ? ` <button class="mini-action" data-action="revoke-session" data-id="${esc(sessionId)}">Revogar</button>` : ''}</td>
        </tr>`;
      }).join('')}</tbody></table></div>` : emptyState('Nenhuma sessão registrada','Não existem sessões disponíveis para o seu perfil no backend.','◉')}</div>`;
  }

  function canRevoke(s) {
    return ['TECHNICIAN','OT_ADMIN'].includes(state.user.role) &&
      ['ACTIVE','PROVISIONING'].includes(s.status);
  }

  function renderAudit() {
    return `<div class="page-heading"><div><h1>Trilha de auditoria</h1><p>Consulta somente leitura dos eventos de segurança e decisões registrados pelo backend.</p></div><button class="btn btn-outline" data-action="reload">↻ Atualizar eventos</button></div>
      <div class="card"><div class="card-pad"><div class="toolbar"><select id="audit-outcome"><option value="">Todos os resultados</option><option value="SUCCESS">Sucesso</option><option value="DENIED">Negado</option></select><input id="audit-type" class="search" placeholder="Filtrar por tipo de evento (ex.: MFA_VERIFIED)" /><button class="btn btn-primary" id="audit-filter">Aplicar filtros</button></div></div>
      <div id="audit-table">${renderAuditTable(state.data.events, state.data.auditTotal || state.data.events.length)}</div></div>`;
  }
  function renderAuditTable(events, total) {
    if (!events.length) return emptyState('Nenhum evento retornado','Use os filtros ou confirme se a conta possui perfil Administrador OT ou Auditor.','⌁');
    return `<div class="table-wrap"><table><thead><tr><th>Data / hora</th><th>Evento</th><th>Ator</th><th>Entidade</th><th>Resultado</th><th></th></tr></thead><tbody>${events.map(e => `<tr><td>${esc(dateTime(e.occurred_at))}</td><td><strong>${esc(e.event_type)}</strong><span class="table-secondary mono">${esc(shortId(e.id))}</span></td><td>${esc(e.actor_email || shortId(e.actor_user_id))}</td><td>${esc(e.entity_type)}<span class="table-secondary mono">${esc(shortId(e.entity_id))}</span></td><td><span class="status ${e.outcome==='SUCCESS'?'approved':'rejected'}">${e.outcome==='SUCCESS'?'Sucesso':'Negado'}</span></td><td><button class="mini-action" data-action="view-event" data-id="${esc(e.id)}">Detalhes</button></td></tr>`).join('')}</tbody></table></div><div style="padding:12px 15px;color:var(--muted);font-size:10px;border-top:1px solid var(--line)">Exibindo ${events.length} de ${total} eventos retornados · limite atual de consulta: 100</div>`;
  }

  function renderCurrentView() {
    if (!state.user) return '';
    switch (state.view) {
      case 'requests': return state.user.role === 'APPROVER' ? renderApprovals() : renderRequests();
      case 'approvals': return renderApprovals();
      case 'operations': return renderOperations();
      case 'sessions': return renderSessions();
      case 'audit': return renderAudit();
      default: return renderDashboard();
    }
  }
  function refreshContent() { const el = $('#page-content'); if (el) el.innerHTML = renderCurrentView(); }

  async function loadData() {
    if (!state.token || !state.user) return;
    state.loading = true;
    const jobs = [
      ['assets', '/assets'], ['orders', '/work-orders'], ['requests', '/access-requests'], ['sessions', '/sessions?limit=200&offset=0'], ['sessionsActive', '/sessions?status=ACTIVE&limit=1&offset=0'],
    ];
    if (['OT_ADMIN','AUDITOR'].includes(state.user.role)) jobs.push(['events','/audit-events?limit=100&offset=0']);
    const results = await Promise.allSettled(jobs.map(([, path]) => api(path)));
    results.forEach((result, i) => {
      const key = jobs[i][0];
      if (result.status === 'fulfilled') {
        if (key === 'events') { state.data.events = result.value.items || []; state.data.auditTotal = result.value.total || 0; } else if (key === 'sessions') { const items = Array.isArray(result.value?.items) ? result.value.items : []; state.data.sessions = items; state.data.sessionsTotal = Number.isFinite(result.value?.total) ? result.value.total : items.length; } else if (key === 'sessionsActive') { state.data.sessionsActiveTotal = Number.isFinite(result.value?.total) ? result.value.total : 0; }
        else state.data[key] = Array.isArray(result.value) ? result.value : [];
      } else {
        console.warn(`Falha ao carregar ${key}:`, result.reason?.message || result.reason);
        state.data[key] = key === 'events' ? [] : state.data[key];
      }
    });
    state.loading = false;
    if (state.view === 'audit' && state.user.role === 'OT_ADMIN' || state.view === 'audit' && state.user.role === 'AUDITOR') {
      // Keep the current filtered table if filters are active.
      if (!$('#audit-type')?.value && !$('#audit-outcome')?.value) refreshContent();
    } else refreshContent();
    updateConnectionBadge();
  }

  async function checkHealth() {
    try { await api('/health', { tokenOverride:null }); state.online = true; }
    catch { state.online = false; }
    updateConnectionBadge();
  }
  function updateConnectionBadge() {
    const c = $('.connection');
    if (c) c.innerHTML = `<span class="dot ${state.online ? 'online' : 'offline'}"></span>${state.online ? 'API conectada' : 'API indisponível'}`;
  }

  function openModal(title, subtitle, body, footer = '') {
    const existing = $('#modal-root'); existing?.remove();
    const wrap = document.createElement('div'); wrap.id = 'modal-root';
    wrap.innerHTML = `<div class="modal-backdrop" data-action="backdrop-close"><section class="modal" role="dialog" aria-modal="true"><header class="modal-head"><div><h2>${title}</h2><p>${subtitle || ''}</p></div><button class="close-btn" data-action="close-modal" aria-label="Fechar">×</button></header><div class="modal-body">${body}</div>${footer ? `<footer class="modal-foot">${footer}</footer>` : ''}</section></div>`;
    document.body.appendChild(wrap);
    $('.modal-backdrop', wrap).addEventListener('click', e => { if (e.target.classList.contains('modal-backdrop')) wrap.remove(); });
  }
  function closeModal() { $('#modal-root')?.remove(); }

  function openRequestModal() {
    if (state.preview) { toast('Prévia local: a criação de solicitações está desativada.'); return; }
    if (!state.data.orders.length || !state.data.assets.length) { toast('Não há ordens de serviço e ativos disponíveis para criar uma solicitação.', 'error'); return; }
    const firstOrder = state.data.orders[0];
    const d1 = new Date(Date.now() + 5*60000); const d2 = new Date(Date.now() + 65*60000);
    const localInput = d => new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,16);
    const body = `<form id="new-request-form"><div class="form-grid">
      <div class="field full"><label for="request-order">Ordem de serviço</label><select id="request-order" name="work_order_id" required>${state.data.orders.map(o => `<option value="${esc(o.id)}" ${o.id===firstOrder.id?'selected':''}>${esc(o.code)} · ${esc(o.description || '')}</option>`).join('')}</select><div class="field-hint">A ordem precisa estar aberta ou em andamento e atribuída ao seu usuário.</div></div>
      <div class="field full"><label for="request-asset">Ativo OT</label><select id="request-asset" name="asset_id" required></select></div>
      <div class="field"><label for="request-profile">Perfil de acesso</label><select id="request-profile" name="access_profile"><option value="READ_ONLY">Somente leitura</option><option value="DIAGNOSTIC">Diagnóstico</option><option value="MAINTENANCE">Manutenção</option></select></div>
      <div class="field"><label for="request-start">Início solicitado</label><input id="request-start" name="requested_start_at" type="datetime-local" value="${localInput(d1)}" required /></div>
      <div class="field"><label for="request-end">Término solicitado</label><input id="request-end" name="requested_end_at" type="datetime-local" value="${localInput(d2)}" required /></div>
      <div class="field full"><label for="request-rationale">Justificativa da intervenção</label><textarea id="request-rationale" name="rationale" minlength="5" maxlength="1500" placeholder="Descreva a atividade que será executada e por que o perfil solicitado é necessário." required></textarea></div>
      </div><div id="criticality-hint" class="info-strip">A criticidade do ativo ou da ordem de serviço determina se será necessária uma ou duas aprovações.</div></form>`;
    openModal('Nova solicitação de acesso', 'Vincule o pedido a uma OS e ao ativo correspondente.', body, '<button class="btn btn-outline" data-action="close-modal">Cancelar</button><button class="btn btn-primary" form="new-request-form" type="submit">Enviar solicitação</button>');
    const updateAsset = () => {
      const order = state.data.orders.find(o => o.id === $('#request-order').value);
      const available = state.data.assets.filter(a => a.id === order?.asset_id);
      $('#request-asset').innerHTML = available.length ? available.map(a => `<option value="${esc(a.id)}">${esc(a.asset_code)} · ${esc(a.name)}</option>`).join('') : '<option value="">Nenhum ativo vinculado à OS</option>';
      const asset = available[0]; const two = Boolean(order?.is_critical || asset?.criticality === 'CRITICAL');
      $('#criticality-hint').textContent = two ? 'Este ativo ou esta OS é crítico(a). O backend exigirá duas aprovações de pessoas distintas.' : 'Pelo cadastro atual, esta solicitação exigirá uma aprovação.';
      $('#criticality-hint').className = two ? 'warning-strip' : 'info-strip';
      if (order) { const toLocal = value => { const d = new Date(value); return new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,16); }; $('#request-start').min = toLocal(order.planned_start_at); $('#request-end').max = toLocal(order.planned_end_at); }
    };
    $('#request-order').addEventListener('change', updateAsset); updateAsset();
    $('#new-request-form').addEventListener('submit', submitRequest);
  }
  async function submitRequest(e) {
    e.preventDefault();
    if (state.preview) { toast('Prévia local: nenhuma solicitação foi enviada.'); return; } const form = new FormData(e.currentTarget); const button = $('button[form="new-request-form"][type="submit"]'); button.disabled = true; button.textContent = 'Enviando…';
    const body = { work_order_id:form.get('work_order_id'), asset_id:form.get('asset_id'), access_profile:form.get('access_profile'), rationale:form.get('rationale'), requested_start_at:new Date(form.get('requested_start_at')).toISOString(), requested_end_at:new Date(form.get('requested_end_at')).toISOString() };
    try { const result = await api('/access-requests', { method:'POST', body }); closeModal(); toast(`Solicitação ${result.request_code} criada. ${result.required_approvals} aprovação(ões) exigida(s).`, 'success'); await loadData(); }
    catch (error) { showError(error); button.disabled = false; button.textContent = 'Enviar solicitação'; }
  }

  function openRequestDetail(id) {
    const r = state.data.requests.find(x => x.id === id); if (!r) return;
    const o = requestOrder(r), a = requestAsset(r);
    const details = [
      ['Código', r.request_code], ['Status', statusLabel(r.status)], ['Solicitante', shortId(r.requester_id)], ['Ordem de serviço', o?.code || r.work_order_id], ['Ativo', a ? `${a.asset_code} · ${a.name}` : r.asset_id], ['Tipo de ativo', assetTypeLabel(a?.asset_type)], ['Criticidade do ativo', a?.criticality], ['Perfil solicitado', accessLabel(r.access_profile)], ['Início solicitado', dateTime(r.requested_start_at)], ['Término solicitado', dateTime(r.requested_end_at)], ['Aprovações necessárias', r.requires_dual_approval ? '2 (ativo ou OS crítica)' : '1'], ['Motivo da criticidade', r.criticality_reason], ['Justificativa', r.rationale]
    ];
    const body = details.map(([k,v]) => `<div class="event-detail"><span>${esc(k)}</span><strong>${esc(v || '—')}</strong></div>`).join('');
    openModal(`Solicitação ${esc(r.request_code || shortId(id))}`, 'Dados retornados pelo backend para este pedido.', body, '<button class="btn btn-outline" data-action="close-modal">Fechar</button>');
  }

  async function submitDecision(id, decision) {
    if (state.preview) { toast('Prévia local: aprovações e recusas estão desativadas.'); return; }
    const r = state.data.requests.find(x => x.id === id); if (!r) return;
    const decisionText = decision === 'APPROVED' ? 'aprovar' : 'recusar';
    const note = window.prompt(`Deseja ${decisionText} a solicitação ${r.request_code}?\nJustificativa (opcional):`, '');
    if (note === null) return;
    try {
      const result = await api(`/access-requests/${encodeURIComponent(id)}/decision`, { method:'POST', body:{ decision, note:note.trim() || null } });
      toast(`Decisão registrada. Status: ${statusLabel(result.request_status)} · ${result.approved_count}/${result.required_approvals} aprovação(ões).`, 'success');
      await loadData();
    } catch (error) { showError(error); }
  }

  async function authorizeRequest(id) {
    if (state.preview) { toast('Prévia local: a concessão de sessão está desativada.'); return; }
    const r = state.data.requests.find(x => x.id === id); if (!r) return;
    try {
      const result = await api(`/access-requests/${encodeURIComponent(id)}/authorize`, { method:'POST' });
      toast(`Retorno do adaptador: sessão ${result.session_id} · ${statusLabel(result.status)}.`, 'success');
      state.view = 'sessions';
      await loadData();
      renderShell();
    } catch (error) {
      if (error.status === 403 && /MFA expirado/i.test(error.message)) {
        state.pendingAuthorization = id; openMfaRefreshModal();
      } else showError(error);
    }
  }
  function openMfaRefreshModal() {
    openModal('Confirme o MFA novamente', 'A verificação MFA anterior ultrapassou a janela de frescor exigida pelo backend.', `<form id="mfa-refresh-form"><div class="field"><label for="refresh-code">Código atual do autenticador</label><input id="refresh-code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="000000" required /></div><div class="alert alert-info">Após atualizar o MFA, a ValidaOT repetirá a autorização da solicitação pendente.</div></form>`, '<button class="btn btn-outline" data-action="close-modal">Cancelar</button><button class="btn btn-primary" form="mfa-refresh-form" type="submit">Validar e continuar</button>');
    $('#mfa-refresh-form').addEventListener('submit', async e => {
      e.preventDefault(); const code = new FormData(e.currentTarget).get('code');
      try {
        const result = await api('/auth/mfa/refresh', { method:'POST', body:{code} });
        state.token = result.access_token; state.mfaVerifiedAt = result.mfa_verified_at; saveAuth();
        const requestId = state.pendingAuthorization; state.pendingAuthorization = null; closeModal();
        toast('MFA renovado. Repetindo autorização…', 'success'); await authorizeRequest(requestId);
      } catch (error) { showError(error); }
    });
  }

  function updateListedSession(sessionId, result) {
    const current = state.data.sessions.find(
      s => (s.session_id || s.external_session_id) === sessionId
    );

    if (!current) return;

    const wasActive = current.status === 'ACTIVE';

    if (result.status !== undefined) current.status = result.status;
    if ('adapter' in result) current.adapter = result.adapter;
    if ('expires_at' in result) current.expires_at = result.expires_at;
    if ('closed_at' in result) current.closed_at = result.closed_at;
    if ('reason' in result) current.reason = result.reason;

    const isActive = current.status === 'ACTIVE';

    if (wasActive !== isActive) {
      state.data.sessionsActiveTotal = Math.max(
        0,
        state.data.sessionsActiveTotal + (isActive ? 1 : -1)
      );
    }
  }

  async function inspectSession(sessionId) {
    if (state.preview) {
      toast('Prévia local: consulta de sessão na API está desativada.');
      return;
    }

    try {
      const result = await api(`/sessions/${encodeURIComponent(sessionId)}`);

      updateListedSession(sessionId, {
        status: result.status,
        adapter: result.adapter,
        expires_at: result.expires_at,
        closed_at: result.closed_at,
        reason: result.reason
      });

      await loadData();

      const body = [
        ['Identificador', result.session_id],
        ['Status', statusLabel(result.status)],
        ['Adaptador', result.adapter],
        ['Expira em', dateTime(result.expires_at)],
        ['Encerrada em', dateTime(result.closed_at)],
        ['Motivo', result.reason]
      ].map(([k,v]) =>
        `<div class="event-detail"><span>${esc(k)}</span><strong>${esc(v || '—')}</strong></div>`
      ).join('');

      openModal(
        'Detalhes da sessão',
        'Situação consultada e sincronizada com o adaptador simulado.',
        body,
        '<button class="btn btn-outline" data-action="close-modal">Fechar</button>'
      );
    } catch (error) {
      showError(error);
    }
  }

  async function revokeSession(sessionId) {
    if (state.preview) {
      toast('Prévia local: revogação de sessão está desativada.');
      return;
    }

    if (!window.confirm(`Confirma a revogação da sessão ${sessionId}?`)) return;

    try {
      const result = await api(
        `/sessions/${encodeURIComponent(sessionId)}/revoke`,
        { method:'POST' }
      );

      updateListedSession(sessionId, {
        status: result.status,
        closed_at: result.closed_at
      });

      await loadData();

      toast(
        `Sessão ${sessionId} ${statusLabel(result.status).toLowerCase()}.`,
        'success'
      );
    } catch (error) {
      showError(error);
    }
  }

  async function lookupSession(e) {
    e.preventDefault();

    if (state.preview) {
      toast('Prévia local: consulta à API desativada. As sessões exibidas são exemplos.');
      return;
    }

    const id = $('#session-id-input').value.trim();

    if (id) await inspectSession(id);
  }

  function openEventDetail(id) {
    const e = state.data.events.find(x => x.id === id); if (!e) return;
    const detailsJson = `<pre style="white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;border-radius:9px;padding:12px;font-size:10px;color:#405366">${esc(JSON.stringify(e.details || {}, null, 2))}</pre>`;
    const body = [['Data / hora',dateTime(e.occurred_at)],['Evento',e.event_type],['Ator',e.actor_email || e.actor_user_id],['Entidade',`${e.entity_type} · ${e.entity_id}`],['Resultado',e.outcome],['Correlation ID',e.correlation_id]].map(([k,v])=>`<div class="event-detail"><span>${esc(k)}</span><strong>${esc(v || '—')}</strong></div>`).join('') + `<div class="field" style="margin-top:14px"><label>Detalhes do evento</label>${detailsJson}</div>`;
    openModal('Detalhes do evento', 'Registro imutável para consulta nesta interface.', body, '<button class="btn btn-outline" data-action="close-modal">Fechar</button>');
  }
  async function filterAudit() {
    const outcome = $('#audit-outcome')?.value || ''; const type = $('#audit-type')?.value.trim() || '';
    if (state.preview) {
      const filtered = state.data.events.filter(e => (!outcome || e.outcome === outcome) && (!type || e.event_type.toLowerCase().includes(type.toLowerCase())));
      $('#audit-table').innerHTML = renderAuditTable(filtered, filtered.length);
      return;
    }
    const params = new URLSearchParams({ limit:'100', offset:'0' }); if (outcome) params.set('outcome', outcome); if (type) params.set('event_type', type);
    try { const result = await api(`/audit-events?${params.toString()}`); state.data.events = result.items || []; state.data.auditTotal = result.total || 0; $('#audit-table').innerHTML = renderAuditTable(state.data.events, state.data.auditTotal); }
    catch (error) { showError(error); }
  }

  async function submitLogin(e) {
    e.preventDefault();
    // Este handler é delegado ao document; e.currentTarget seria o document.
    // O formulário que originou o evento está em e.target.
    const form = e.target;
    const f = new FormData(form);
    const button = $('button[type="submit"]', form);
    if (button) { button.disabled = true; button.textContent = 'Validando…'; }
    try {
      const result = await api('/auth/login', { method:'POST', tokenOverride:null, body:{ email:f.get('email'), password:f.get('password') } });
      if (result.status === 'MFA_SETUP_REQUIRED' || result.status === 'MFA_REQUIRED') {
        state.challengeToken = result.challenge_token; state.challengeMode = result.status === 'MFA_SETUP_REQUIRED' ? 'setup' : 'verify';
        if (state.challengeMode === 'setup') {
          const setup = await api('/auth/mfa/setup', { method:'POST', tokenOverride:state.challengeToken });
          state._mfaSetupData = setup;
          renderMfa('setup', setup);
        } else renderMfa('verify');
      } else if (result.status === 'AUTHENTICATED') {
        state.token = result.access_token; state.user = result.user; state.mfaVerifiedAt = null; state.challengeToken = null; saveAuth();
        state.view = 'dashboard'; await startApp();
      } else throw new Error('O backend retornou um estado de autenticação não reconhecido.');
    } catch (error) { renderLogin(error.message || 'Falha ao autenticar.'); }
  }
  async function submitMfa(e) {
    e.preventDefault();
    // O evento também é delegado ao document; usar o formulário de origem.
    const form = e.target;
    const code = new FormData(form).get('code');
    const setup = state.challengeMode === 'setup';
    const endpoint = setup ? '/auth/mfa/confirm' : '/auth/mfa/verify';
    const button = $('button[type="submit"]', form);
    if (button) { button.disabled = true; button.textContent = 'Verificando…'; }
    try {
      const result = await api(endpoint, { method:'POST', tokenOverride:state.challengeToken, body:{code} });
      state.token = result.access_token; state.user = result.user; state.mfaVerifiedAt = result.mfa_verified_at || null; state.challengeToken = null; state.challengeMode = null; saveAuth();
      toast(setup ? 'MFA configurado e habilitado.' : 'Identidade confirmada.', 'success'); state.view='dashboard'; await startApp();
    } catch (error) {
      const title = setup ? 'setup' : 'verify';
      const data = state._mfaSetupData || {};
      renderMfa(title, data, error.message || 'Não foi possível validar o código.');
    }
  }

  async function startApp() {
    renderShell();
    await checkHealth();
    await loadData();
  }
  async function reloadCurrent() {
    if (state.preview) { toast('Prévia local: os dados são exemplos estáticos e não serão atualizados pela API.'); return; }
    await checkHealth(); await loadData();
    if (state.view === 'audit') await filterAudit();
    toast('Dados atualizados.', 'success');
  }
  function navTo(view) {
    const allowed = visibleNav().some(i => i.id === view) || view === 'dashboard';
    if (!allowed) { toast('Seu perfil não possui acesso a esta área.', 'error'); return; }
    state.view = view; state.mobileNavOpen = false; renderShell();
    if (view === 'audit') filterAudit();
  }

  document.addEventListener('submit', e => {
    if (e.target.id === 'login-form') submitLogin(e);
    else if (e.target.id === 'mfa-form') submitMfa(e);
    else if (e.target.id === 'session-lookup') lookupSession(e);
  });
  document.addEventListener('click', async e => {
    const nav = e.target.closest('[data-nav]');
    if (nav) { navTo(nav.dataset.nav); return; }
    const actionEl = e.target.closest('[data-action]'); if (!actionEl) return;
    const { action, id, decision } = actionEl.dataset;
    if (action === 'close-modal') closeModal();
    else if (action === 'backdrop-close' && e.target.classList.contains('modal-backdrop')) closeModal();
    else if (action === 'new-request') openRequestModal();
    else if (action === 'reload') await reloadCurrent();
    else if (action === 'view-request') openRequestDetail(id);
    else if (action === 'decision') await submitDecision(id, decision);
    else if (action === 'authorize') await authorizeRequest(id);
    else if (action === 'inspect-session') await inspectSession(id);
    else if (action === 'revoke-session') await revokeSession(id);
    else if (action === 'view-event') openEventDetail(id);
    else if (action === 'clear-session-cache') { if (state.preview) { toast('Prévia local: a lista de exemplos não será alterada.'); return; } if (confirm('Limpar a lista de sessões armazenada somente nesta aba? Isso não altera sessões no backend.')) { state.sessions=[]; saveSessions(); refreshContent(); } }
  });
  document.addEventListener('click', e => {
    const previewRole = e.target.closest('[data-preview-role]');
    if (previewRole) { enterPreview(previewRole.dataset.previewRole); return; }
    if (e.target.id === 'logout-btn') {
      if (state.preview) exitPreview();
      else { clearAuth(); renderLogin(); }
    }
    if (e.target.id === 'switch-preview-role') { exitPreview(); return; }
    if (e.target.id === 'mobile-menu') { state.mobileNavOpen = !state.mobileNavOpen; $('#sidebar')?.classList.toggle('open', state.mobileNavOpen); $('#mobile-overlay')?.classList.toggle('show', state.mobileNavOpen); }
    if (e.target.id === 'mobile-overlay') { state.mobileNavOpen=false; $('#sidebar')?.classList.remove('open'); $('#mobile-overlay')?.classList.remove('show'); }
    if (e.target.id === 'audit-filter') filterAudit();
  });
  document.addEventListener('input', e => {
    if (e.target.id === 'request-search' || e.target.id === 'request-status') {
      const q = ($('#request-search')?.value || '').toLowerCase(); const status = $('#request-status')?.value || '';
      const filtered = state.data.requests.filter(r => {
        const a=requestAsset(r), o=requestOrder(r); const hay=[r.request_code,a?.asset_code,a?.name,o?.code,r.rationale].join(' ').toLowerCase();
        return (!q || hay.includes(q)) && (!status || r.status === status);
      });
      $('#request-table').innerHTML = renderRequestTable(filtered);
    }
  });
  document.addEventListener('change', e => {
    if (e.target.id === 'request-status') e.target.dispatchEvent(new Event('input', {bubbles:true}));
  });

  async function boot() {
    const auth = safeJson(sessionStorage.getItem(AUTH_KEY), null);
    if (!auth?.token || !auth?.user) { renderLogin(); return; }
    state.token = auth.token; state.user = auth.user; state.mfaVerifiedAt = auth.mfaVerifiedAt || null;
    try {
      const me = await api('/auth/me');
      state.user = me.user; state.mfaVerifiedAt = me.mfa_verified_at || state.mfaVerifiedAt; saveAuth();
      await startApp();
    } catch {
      clearAuth(); renderLogin('Sua sessão expirou ou não pôde ser validada. Entre novamente.');
    }
  }
  boot();
})();
