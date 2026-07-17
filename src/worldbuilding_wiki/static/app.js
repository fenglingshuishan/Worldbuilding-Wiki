const state = { info: null, entries: [], current: null };
const content = document.querySelector("#content");

const TYPE_LABELS = {
  character: "人物", location: "地点", organization: "组织", event: "事件",
  group: "群体", culture: "文化", rule: "规则", artifact: "物件",
  concept: "概念", source: "来源",
};
const STATUS_LABELS = { canon: "正史", draft: "草稿", rumor: "传闻", deprecated: "废弃" };
const RELATION_LABELS = {
  related_to: "相关", located_in: "位于", born_in: "出生于", member_of: "隶属于",
  leads: "领导", parent_of: "亲代", ally_of: "同盟", enemy_of: "敌对",
  participates_in: "参与", causes: "导致", precedes: "早于", uses: "使用",
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).message || message; } catch (_) { /* ignore */ }
    throw new Error(message);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response;
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

function toast(message, kind = "") {
  const element = document.createElement("div");
  element.className = `toast ${kind}`;
  element.textContent = message;
  document.querySelector("#toast-region").append(element);
  setTimeout(() => element.remove(), 3800);
}

function confirmAction({title, message, confirmLabel = "确认", expectedText = "", danger = false}) {
  const dialog = document.querySelector("#action-dialog");
  const close = document.querySelector("#dialog-close");
  const cancel = document.querySelector("#dialog-cancel");
  const confirm = document.querySelector("#dialog-confirm");
  const field = document.querySelector("#dialog-confirmation-field");
  const input = document.querySelector("#dialog-confirmation");
  document.querySelector("#dialog-title").textContent = title;
  document.querySelector("#dialog-message").textContent = message;
  document.querySelector("#dialog-confirmation-label").textContent = expectedText ? `输入“${expectedText}”以继续` : "";
  confirm.textContent = confirmLabel;
  confirm.className = `button ${danger ? "danger" : "primary"}`;
  field.hidden = !expectedText;
  input.value = "";
  confirm.disabled = Boolean(expectedText);

  return new Promise(resolve => {
    const update = () => { confirm.disabled = Boolean(expectedText) && input.value !== expectedText; };
    const finish = accepted => {
      close.removeEventListener("click", reject);
      cancel.removeEventListener("click", reject);
      confirm.removeEventListener("click", accept);
      input.removeEventListener("input", update);
      dialog.removeEventListener("cancel", reject);
      if (dialog.open) dialog.close();
      resolve(accepted);
    };
    const reject = event => { event?.preventDefault(); finish(false); };
    const accept = event => { event.preventDefault(); finish(true); };
    close.addEventListener("click", reject);
    cancel.addEventListener("click", reject);
    confirm.addEventListener("click", accept);
    input.addEventListener("input", update);
    dialog.addEventListener("cancel", reject);
    dialog.showModal();
    (expectedText ? input : confirm).focus();
  });
}

function setBusy(button, busy, label = "处理中……") {
  if (!button) return;
  if (busy) { button.dataset.label = button.textContent; button.textContent = label; button.disabled = true; }
  else { button.textContent = button.dataset.label || button.textContent; button.disabled = false; }
}

function downloadResponse(response) {
  return response.blob().then(blob => {
    const disposition = response.headers.get("content-disposition") || "";
    const encoded = disposition.match(/filename\*=utf-8''([^;]+)/i);
    const plain = disposition.match(/filename="?([^";]+)"?/i);
    const filename = encoded ? decodeURIComponent(encoded[1]) : (plain ? plain[1] : "download.zip");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

function typeOptions(selected = "concept") {
  return Object.entries(TYPE_LABELS).map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}
function statusOptions(selected = "draft") {
  return Object.entries(STATUS_LABELS).map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}
function badge(status) { return `<span class="badge ${escapeHtml(status)}">${STATUS_LABELS[status] || escapeHtml(status)}</span>`; }

async function refreshInfo() {
  state.info = await api("/api/info");
  const indicator = document.querySelector("#vault-indicator");
  indicator.textContent = state.info.ready ? state.info.vault.name : "尚未打开世界库";
  document.querySelector("#new-entry-button").style.visibility = state.info.ready ? "visible" : "hidden";
  const search = document.querySelector("#search-input");
  search.disabled = !state.info.ready;
  search.placeholder = state.info.ready ? "搜索标题、别名、正文或标签" : "请先创建或打开世界库";
  document.querySelectorAll("[data-nav]").forEach(link => {
    const disabled = !state.info.ready && link.dataset.nav !== "home";
    link.classList.toggle("disabled", disabled);
    link.setAttribute("aria-disabled", disabled ? "true" : "false");
  });
  if (state.info.ready) {
    const checks = await api("/api/checks");
    document.querySelector("#check-badge").textContent = checks.length || "";
  } else {
    document.querySelector("#check-badge").textContent = "";
  }
}

function routeName() {
  const part = location.hash.replace(/^#\//, "").split("/")[0];
  return part || "home";
}

async function router() {
  document.body.classList.remove("menu-open");
  await refreshInfo();
  const activeRoute = state.info.ready ? routeName() : "home";
  document.querySelectorAll("[data-nav]").forEach(link => {
    const active = link.dataset.nav === activeRoute;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (!state.info.ready) return renderWelcome();
  const rawRoute = location.hash.replace(/^#\/?/, "");
  const [routePath, routeQuery = ""] = rawRoute.split("?");
  const parts = routePath.split("/").filter(Boolean);
  const params = new URLSearchParams(routeQuery);
  try {
    if (!parts.length) return renderHome();
    if (parts[0] === "entries") return renderEntries(params.get("q") || "");
    if (parts[0] === "entry" && parts[1]) return renderEntry(parts[1]);
    if (parts[0] === "edit" && parts[1]) return renderEditor(parts[1]);
    if (parts[0] === "new") return renderEditor(null, params.get("template"));
    if (parts[0] === "templates") return renderTemplates();
    if (parts[0] === "timeline") return renderTimeline();
    if (parts[0] === "relations") return renderRelations();
    if (parts[0] === "checks") return renderChecks();
    if (parts[0] === "transfer") return renderTransfer();
    if (parts[0] === "settings") return renderSettings();
    content.innerHTML = `<div class="empty"><h2>页面不存在</h2><a href="#/">返回总览</a></div>`;
  } catch (error) {
    content.innerHTML = `<div class="empty"><h2>无法载入页面</h2><p>${escapeHtml(error.message)}</p><button class="button" onclick="location.reload()">重新加载</button></div>`;
    toast(error.message, "error");
  }
  content.focus();
}

function renderWelcome() {
  content.innerHTML = `<section class="welcome">
    <div class="hero"><span class="eyebrow">世界库 / 开始</span>
      <h1>选择一个世界库</h1>
      <p>正文保存在独立的 Markdown 目录中。程序只维护可重建索引，不接管你的原始内容。</p>
    </div>
    <div class="welcome-grid">
      <div class="welcome-option"><h2>新建世界库</h2><p class="muted">使用默认安全位置，也可稍后迁移。</p>
        <form id="create-vault-form"><input name="name" required placeholder="世界库名称"><input name="world_name" required value="主世界" placeholder="第一个世界名称"><button class="button primary">创建并打开</button></form></div>
      <div class="welcome-option"><h2>打开现有目录</h2><p class="muted">目录内应存在 <code>vault.yaml</code>。</p>
        <form id="open-vault-form"><input name="path" required placeholder="世界库完整路径"><button class="button">打开目录</button></form></div>
      <div class="welcome-option"><h2>导入传输包</h2><p class="muted">校验 <code>.worldvault</code> 后创建新世界库。</p>
        <form id="welcome-import-form"><input name="name" required value="导入的世界库"><input name="file" type="file" accept=".worldvault,.zip" required><button class="button">检查并导入</button></form></div>
    </div></section>`;
  document.querySelector("#create-vault-form").addEventListener("submit", createVault);
  document.querySelector("#open-vault-form").addEventListener("submit", openVault);
  document.querySelector("#welcome-import-form").addEventListener("submit", event => importFile(event, "new"));
}

async function createVault(event) {
  event.preventDefault(); const button = event.submitter; setBusy(button, true);
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try { await api("/api/vaults", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}); toast("世界库已创建"); location.hash = "#/"; await router(); }
  catch (error) { toast(error.message, "error"); } finally { setBusy(button, false); }
}

async function openVault(event) {
  event.preventDefault(); const button = event.submitter; setBusy(button, true);
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try { await api("/api/vaults/open", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}); toast("世界库已打开"); location.hash = "#/"; await router(); }
  catch (error) { toast(error.message, "error"); } finally { setBusy(button, false); }
}

async function renderHome() {
  const dashboard = await api("/api/dashboard");
  const summary = dashboard.summary;
  const checkTotal = Object.values(dashboard.checks).reduce((sum, value) => sum + value, 0);
  content.innerHTML = `<section class="workspace-hero"><div><span class="eyebrow">创作工作区 / ONLINE</span><h1>${escapeHtml(state.info.vault.name)}</h1>
      <p>${state.info.worlds.length} 个世界正在同一套知识体系中演进。内容、关系和质量信号都汇聚在这里。</p></div>
      <div class="hero-actions"><a class="button primary" href="#/new">＋ 创建内容</a><a class="button" href="#/templates">从模板开始</a></div></section>
    <section class="metric-grid">
      ${metricCard(summary.entries, "知识条目", "全库规模", "accent")}
      ${metricCard(summary.canonical, "正史内容", `${summary.entries ? Math.round(summary.canonical * 100 / summary.entries) : 0}% 已确认`, "success")}
      ${metricCard(summary.drafts, "待推进草稿", "创作队列", summary.drafts ? "warning" : "success")}
      ${metricCard(summary.relations + summary.links, "知识连接", `${summary.relations} 条语义关系`, "accent")}
      ${metricCard(`${summary.content_health}%`, "内容成熟度", "正文与元数据覆盖", summary.content_health >= 70 ? "success" : "warning")}
    </section>
    <section class="dashboard-grid">
      <div class="panel span-2"><div class="panel-header"><div><span class="eyebrow">CONTENT OPERATIONS</span><h2>最近活动</h2></div><a href="#/entries">管理内容库 →</a></div>${managementRows(dashboard.recent, false)}</div>
      <div class="panel"><div class="panel-header"><div><span class="eyebrow">PORTFOLIO</span><h2>内容构成</h2></div></div>${distributionBars(dashboard.by_type, TYPE_LABELS)}</div>
      <div class="panel"><div class="panel-header"><div><span class="eyebrow">WORKFLOW</span><h2>创作状态</h2></div></div>${distributionBars(dashboard.by_status, STATUS_LABELS)}<a class="panel-link" href="#/checks">${checkTotal} 个质量信号待查看 →</a></div>
      <div class="panel"><div class="panel-header"><div><span class="eyebrow">FOCUS QUEUE</span><h2>下一步建议</h2></div></div>${attentionRows(dashboard.needs_attention)}</div>
      <div class="panel"><div class="panel-header"><div><span class="eyebrow">TAXONOMY</span><h2>热门标签</h2></div></div><div class="tag-cloud">${dashboard.top_tags.map(item=>`<a href="#/entries?q=${encodeURIComponent(item.name)}"><span>${escapeHtml(item.name)}</span><b>${item.count}</b></a>`).join("") || "<span class='muted'>暂无标签</span>"}</div></div>
    </section>`;
}

function metricCard(value, label, hint, tone) {
  return `<article class="metric-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(hint)}</small></article>`;
}

function distributionBars(values, labels) {
  const rows = Object.entries(values); const max = Math.max(...rows.map(([, count]) => count), 1);
  return `<div class="distribution">${rows.map(([name,count])=>`<div><span>${escapeHtml(labels[name] || name)}</span><i><b style="width:${Math.max(5, count/max*100)}%"></b></i><strong>${count}</strong></div>`).join("") || "<p class='muted'>暂无数据</p>"}</div>`;
}

function attentionRows(entries) {
  if (!entries.length) return `<div class="empty compact"><h3>队列已清空</h3><p>当前内容都有足够的正文或已完成确认。</p></div>`;
  return `<div class="focus-list">${entries.slice(0,5).map(item=>`<a href="#/edit/${item.id}"><span>${badge(item.status)}<strong>${escapeHtml(item.title)}</strong></span><small>${escapeHtml(item.reason)} →</small></a>`).join("")}</div>`;
}

function entryCards(entries) {
  if (!entries.length) return emptySmall("当前没有条目。");
  return `<div class="entry-grid">${entries.map(entry => `<a class="entry-card" href="#/entry/${entry.id}">${badge(entry.status)}<h3>${escapeHtml(entry.title)}</h3><p>${TYPE_LABELS[entry.type] || entry.type} · ${escapeHtml((entry.tags || []).join(" / ") || "未添加标签")}</p></a>`).join("")}</div>`;
}
function emptySmall(message) { return `<div class="empty">${escapeHtml(message)}</div>`; }

function managementRows(entries, selectable = true) {
  if (!entries.length) return emptySmall("当前没有符合条件的条目。");
  return `<div class="management-list ${selectable ? "" : "read-only"}">${entries.map(entry=>`<div class="management-row">
    ${selectable ? `<label class="select-box" aria-label="选择 ${escapeHtml(entry.title)}"><input type="checkbox" data-entry-id="${escapeHtml(entry.id)}"><i></i></label>` : ""}
    <a class="entry-identity" href="#/entry/${entry.id}"><span class="type-mark ${entry.type}">${escapeHtml((TYPE_LABELS[entry.type] || entry.type).slice(0,1))}</span><span><strong>${escapeHtml(entry.title)}</strong><small>${TYPE_LABELS[entry.type] || entry.type} · ${escapeHtml(worldLabel(entry.world))}</small></span></a>
    <div class="entry-tags">${(entry.tags || []).slice(0,3).map(tag=>`<span>${escapeHtml(tag)}</span>`).join("") || "<span>未分类</span>"}</div>
    ${badge(entry.status)}<time>${formatDate(entry.updated_at)}</time><a class="row-action" href="#/edit/${entry.id}" aria-label="编辑">•••</a>
  </div>`).join("")}</div>`;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value); if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat("zh-CN", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"}).format(date);
}

function worldLabel(worldId) {
  return state.info?.worlds?.find(world=>world.id===worldId)?.name || worldId;
}

async function renderEntries(initialQuery = "") {
  const worldOptions = state.info.worlds.map(world=>`<option value="${escapeHtml(world.id)}">${escapeHtml(world.name)}</option>`).join("");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">CONTENT LIBRARY / 02</span><h1>内容库</h1><p>集中检索、筛选和治理整个世界库的知识资产。</p></div><div class="actions"><a class="button" href="#/templates">浏览模板</a><a class="button primary" href="#/new">＋ 新建条目</a></div></div>
    <section class="library-toolbar"><form id="entry-filters" class="filters"><input name="q" value="${escapeHtml(initialQuery)}" placeholder="标题、别名、正文或标签"><select name="world"><option value="">全部世界</option>${worldOptions}</select><select name="type"><option value="">全部类型</option>${typeOptions("")}</select><select name="status"><option value="">全部状态</option>${statusOptions("")}</select><button class="button">应用筛选</button></form>
    <div class="library-meta"><label class="select-all"><input id="select-all" type="checkbox"> 全选当前结果</label><span id="result-count"></span></div></section>
    <section id="bulk-bar" class="bulk-bar" hidden><strong><span id="selected-count">0</span> 项已选择</strong><select id="bulk-status"><option value="">保持当前状态</option>${statusOptions("")}</select><input id="bulk-tags" placeholder="添加标签，用逗号分隔"><button id="apply-bulk" class="button primary small">批量应用</button><button id="clear-selection" class="button small">取消选择</button></section>
    <div id="entry-results"></div>`;
  const form = document.querySelector("#entry-filters");
  async function load() {
    const params = new URLSearchParams(new FormData(form));
    const entries = await api(`/api/entries?${params}`);
    state.entries = entries;
    document.querySelector("#result-count").textContent = `${entries.length} 个结果`;
    document.querySelector("#entry-results").innerHTML = managementRows(entries);
    bindSelection();
  }
  form.addEventListener("submit", event => { event.preventDefault(); load().catch(error => toast(error.message, "error")); });
  function selectedIds() { return [...document.querySelectorAll("[data-entry-id]:checked")].map(item=>item.dataset.entryId); }
  function updateBulk() { const ids=selectedIds(); document.querySelector("#bulk-bar").hidden=!ids.length; document.querySelector("#selected-count").textContent=ids.length; document.querySelector("#select-all").checked=Boolean(state.entries.length)&&ids.length===state.entries.length; }
  function bindSelection() { document.querySelectorAll("[data-entry-id]").forEach(box=>box.addEventListener("change",updateBulk)); updateBulk(); }
  document.querySelector("#select-all").addEventListener("change",event=>{document.querySelectorAll("[data-entry-id]").forEach(box=>box.checked=event.currentTarget.checked);updateBulk();});
  document.querySelector("#clear-selection").addEventListener("click",()=>{document.querySelectorAll("[data-entry-id]").forEach(box=>box.checked=false);updateBulk();});
  document.querySelector("#apply-bulk").addEventListener("click",async event=>{const entry_ids=selectedIds();if(!entry_ids.length)return;const button=event.currentTarget;setBusy(button,true,"应用中……");try{await api("/api/entries/bulk",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({entry_ids,status:document.querySelector("#bulk-status").value||null,add_tags:splitList(document.querySelector("#bulk-tags").value)})});toast(`已更新 ${entry_ids.length} 个条目`);await load();}catch(error){toast(error.message,"error");}finally{setBusy(button,false);}});
  await load();
}

async function renderEntry(id) {
  const data = await api(`/api/entries/${encodeURIComponent(id)}`); state.current = data;
  const entry = data.entry;
  const links = data.links.map(item => item.target_id ? `<a href="#/entry/${item.target_id}">${escapeHtml(item.title || item.target_ref)}</a>` : `<span class="danger-text">${escapeHtml(item.target_ref)}（未解析）</span>`).join("");
  const relations = data.relations.map(item => `<li><strong>${escapeHtml(item.predicate)}</strong> → ${item.object_title ? `<a href="#/entry/${item.object}">${escapeHtml(item.object_title)}</a>` : escapeHtml(item.object)}</li>`).join("");
  content.innerHTML = `<div class="page-heading"><div><a href="#/entries">← 全部条目</a></div><div class="actions"><a class="button" href="#/edit/${entry.id}">编辑</a><button id="archive-entry" class="button danger">标记废弃</button></div></div>
    <div class="article-layout"><article class="article"><span class="eyebrow">${TYPE_LABELS[entry.type] || entry.type} · ${STATUS_LABELS[entry.status] || entry.status}</span><h1>${escapeHtml(entry.title)}</h1>
      <div class="metadata-line"><span>${escapeHtml(entry.id)}</span><span>世界：${escapeHtml(entry.world)}</span><span>分支：${escapeHtml(entry.branch)}</span>${(entry.tags || []).map(tag=>`<span>#${escapeHtml(tag)}</span>`).join("")}</div><hr><div class="article-body">${data.rendered_html || "<p class='muted'>尚无正文。</p>"}</div></article>
      <aside class="context-column"><section class="panel"><h3>反向链接</h3><ul class="context-list">${data.backlinks.map(item=>`<li><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></li>`).join("") || "<li class='muted'>暂无</li>"}</ul></section>
      <section class="panel"><h3>提及</h3><div class="context-list">${links || "<span class='muted'>暂无</span>"}</div></section>
      <section class="panel"><h3>关系</h3><ul class="context-list">${relations || "<li class='muted'>暂无</li>"}</ul></section>
      <section class="panel"><h3>检查</h3><ul class="context-list">${data.checks.map(item=>`<li>${escapeHtml(item.message)}</li>`).join("") || "<li class='success-text'>没有发现问题</li>"}</ul></section></aside></div>`;
  document.querySelector("#archive-entry").addEventListener("click", async () => {
    if (!await confirmAction({title:"标记为废弃",message:"正文不会被删除，但该条目将不再作为当前有效设定。",confirmLabel:"确认标记",danger:true})) return;
    try { await api(`/api/entries/${entry.id}?expected_hash=${entry.content_hash}`, {method:"DELETE"}); toast("条目已标记为废弃"); await renderEntry(entry.id); } catch (error) { toast(error.message,"error"); }
  });
}

async function renderEditor(id = null, templateId = null) {
  let entry = {type:"concept", status:"draft", title:"", aliases:[], tags:[], branch:"main", body:"", relations:[], time:null};
  if (id) entry = (await api(`/api/entries/${id}`)).entry;
  let activeTemplate = null;
  if (!id && templateId) {
    const templates = await api("/api/templates");
    activeTemplate = templates.find(item=>item.id===templateId) || null;
    if (activeTemplate) entry = {...entry,type:activeTemplate.type,status:activeTemplate.status,tags:activeTemplate.tags,body:activeTemplate.body};
  }
  const allEntries = await api("/api/entries?limit=1000");
  const worldOptions = state.info.worlds.map(world=>`<option value="${escapeHtml(world.id)}" ${(entry.world || state.info.worlds[0].id) === world.id ? "selected" : ""}>${escapeHtml(world.name)}</option>`).join("");
  const relations = entry.relations || [];
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">${id ? "条目编辑" : "条目创建"}</span><h1>${id ? "编辑条目" : "新建条目"}</h1><p>正文支持 Markdown 和 <code>[[Wiki 链接]]</code>。</p></div></div>
    ${activeTemplate ? `<div class="template-notice"><span>正在使用模板</span><strong>${escapeHtml(activeTemplate.name)}</strong><a href="#/templates">更换模板</a></div>` : ""}
    <form id="entry-form" class="form-card"><div class="form-grid">
      <div class="field full"><label>标题</label><input name="title" required maxlength="160" value="${escapeHtml(entry.title)}" autofocus></div>
      <div class="field"><label>类型</label><select name="type" ${id ? "disabled" : ""}>${typeOptions(entry.type)}</select></div>
      <div class="field"><label>内容状态</label><select name="status">${statusOptions(entry.status)}</select></div>
      <div class="field"><label>所属世界</label><select name="world" ${id ? "disabled" : ""}>${worldOptions}</select></div>
      <div class="field"><label>时间线分支</label><input name="branch" value="${escapeHtml(entry.branch || "main")}" placeholder="main"></div>
      <div class="field"><label>别名</label><input name="aliases" value="${escapeHtml((entry.aliases || []).join(", "))}" placeholder="用逗号分隔"></div>
      <div class="field"><label>标签</label><input name="tags" value="${escapeHtml((entry.tags || []).join(", "))}" placeholder="用逗号分隔"></div>
      <div class="field"><label>时间显示</label><input name="time_display" value="${escapeHtml(entry.time?.display || "")}" placeholder="例如：星历 312 年霜月下旬"></div>
      <div class="field"><label>排序序号范围</label><div style="display:flex;gap:8px"><input name="earliest" type="number" value="${entry.time?.earliest_ordinal ?? ""}" placeholder="最早"><input name="latest" type="number" value="${entry.time?.latest_ordinal ?? ""}" placeholder="最晚"></div></div>
      <div class="field full"><label>语义关系</label><div id="relations"></div><button type="button" id="add-relation" class="button small">＋ 添加关系</button><small>目标填写稳定条目 ID；普通提及请直接在正文中使用 Wiki 链接。</small></div>
      <div class="field full"><label>正文</label><textarea name="body" placeholder="输入 Markdown 正文">${escapeHtml(entry.body)}</textarea></div>
      <div class="field full"><label>图片、地图或附件</label><div style="display:flex;gap:8px;align-items:center"><input id="asset-file" type="file" accept="image/*,.pdf,.mp3,.ogg,.wav,.txt,.csv"><button type="button" id="upload-asset" class="button small">上传并插入正文</button></div><small>附件保存在当前世界的 assets 目录，并随世界传输包一起迁移。</small></div>
    </div><div class="actions"><button class="button primary">保存条目</button><a class="button" href="${id ? `#/entry/${id}` : "#/entries"}">取消</a></div></form>`;
  const relationRoot = document.querySelector("#relations");
  function addRelation(relation = {}) {
    const row = document.createElement("div"); row.className = "relation-row";
    const predicates = Object.entries(RELATION_LABELS).map(([value,label])=>`<option value="${value}" ${(relation.predicate || "related_to")===value?"selected":""}>${label} · ${value}</option>`).join("");
    const targets = [`<option value="">选择目标条目</option>`,...allEntries.filter(item=>item.id!==id).map(item=>`<option value="${escapeHtml(item.id)}" ${relation.object===item.id?"selected":""}>${escapeHtml(item.title)} · ${TYPE_LABELS[item.type]||item.type}</option>`)].join("");
    row.innerHTML = `<select data-key="predicate">${predicates}</select><select data-key="object">${targets}</select><button type="button" class="button small danger">移除</button>`;
    row.querySelector("button").addEventListener("click", () => row.remove()); relationRoot.append(row);
  }
  relations.forEach(addRelation); document.querySelector("#add-relation").addEventListener("click", () => addRelation());
  document.querySelector("#upload-asset").addEventListener("click", async event => {
    const file = document.querySelector("#asset-file").files[0]; if (!file) return toast("请先选择附件", "error");
    const button = event.currentTarget; setBusy(button,true,"上传中……");
    try { const world = entry.world || state.info.worlds[0].id; const result = await api(`/api/assets?world=${encodeURIComponent(world)}&filename=${encodeURIComponent(file.name)}`, {method:"POST",headers:{"Content-Type":file.type || "application/octet-stream"},body:file});
      const textarea = document.querySelector('[name="body"]'); textarea.setRangeText(`\n${result.markdown}\n`, textarea.selectionStart, textarea.selectionEnd, "end"); toast("附件已插入正文");
    } catch(error) { toast(error.message,"error"); } finally { setBusy(button,false); }
  });
  document.querySelector("#entry-form").addEventListener("submit", async event => {
    event.preventDefault(); const button = event.submitter; setBusy(button,true,"保存中……");
    const form = new FormData(event.currentTarget); const earliest = form.get("earliest"), latest = form.get("latest"), display = form.get("time_display").trim();
    const payload = { title:form.get("title"), type:id ? entry.type : form.get("type"), world:id ? entry.world : form.get("world"), status:form.get("status"), aliases:splitList(form.get("aliases")), tags:splitList(form.get("tags")), branch:form.get("branch").trim() || "main", body:form.get("body"), expected_hash:entry.content_hash,
      relations:[...relationRoot.querySelectorAll(".relation-row")].map(row=>({predicate:row.querySelector('[data-key="predicate"]').value.trim(), object:row.querySelector('[data-key="object"]').value.trim()})).filter(item=>item.object),
      time: display || earliest || latest ? {display, earliest_ordinal:earliest === "" ? null : Number(earliest), latest_ordinal:latest === "" ? null : Number(latest), precision:"custom"} : null };
    try { const result = await api(id ? `/api/entries/${id}` : "/api/entries", {method:id?"PUT":"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); toast("条目已保存"); location.hash = `#/entry/${result.entry.id}`; }
    catch(error){ toast(error.message,"error"); } finally { setBusy(button,false); }
  });
}
function splitList(value) { return String(value || "").split(/[,，]/).map(x=>x.trim()).filter(Boolean); }

async function renderTemplates() {
  const templates = await api("/api/templates");
  const builtin = templates.filter(item=>item.builtin); const custom = templates.filter(item=>!item.builtin);
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">CONTENT BLUEPRINTS / 03</span><h1>模板中心</h1><p>把稳定的创作方法沉淀为可复用蓝图，并随世界库一起迁移。</p></div><button id="toggle-template-form" class="button primary">＋ 新建模板</button></div>
    <section id="template-form-panel" class="form-card template-builder" hidden><div class="panel-header"><div><span class="eyebrow">CUSTOM BLUEPRINT</span><h2>创建自定义模板</h2></div></div><form id="template-form" class="form-grid">
      <div class="field"><label>模板名称</label><input name="name" required maxlength="100" placeholder="例如：王国档案"></div><div class="field"><label>默认类型</label><select name="type">${typeOptions()}</select></div>
      <div class="field full"><label>用途说明</label><input name="description" maxlength="300" placeholder="告诉未来的自己何时使用它"></div><div class="field full"><label>默认标签</label><input name="tags" placeholder="用逗号分隔"></div>
      <div class="field full"><label>正文骨架</label><textarea name="body" placeholder="## 概述\n\n## 核心内容"></textarea></div><div class="actions full"><button class="button primary">保存模板</button><button type="button" id="cancel-template" class="button">取消</button></div></form></section>
    <section class="template-section"><div class="section-heading"><div><span class="eyebrow">CURATED</span><h2>内置创作框架</h2></div><span>${builtin.length} 个模板</span></div><div class="template-grid">${builtin.map(templateCard).join("")}</div></section>
    <section class="template-section"><div class="section-heading"><div><span class="eyebrow">YOUR SYSTEM</span><h2>世界库模板</h2></div><span>${custom.length} 个模板</span></div>${custom.length?`<div class="template-grid">${custom.map(templateCard).join("")}</div>`:emptySmall("还没有自定义模板。将你反复使用的提纲保存下来，下次可直接开始写作。")}</section>`;
  const panel=document.querySelector("#template-form-panel");
  document.querySelector("#toggle-template-form").addEventListener("click",()=>{panel.hidden=!panel.hidden;if(!panel.hidden)panel.querySelector("input").focus();});
  document.querySelector("#cancel-template").addEventListener("click",()=>panel.hidden=true);
  document.querySelector("#template-form").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;setBusy(button,true,"保存中……");const form=new FormData(event.currentTarget);try{await api("/api/templates",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:form.get("name"),description:form.get("description"),type:form.get("type"),tags:splitList(form.get("tags")),body:form.get("body")})});toast("模板已保存到世界库");await renderTemplates();}catch(error){toast(error.message,"error");}finally{setBusy(button,false);}});
  document.querySelectorAll("[data-delete-template]").forEach(button=>button.addEventListener("click",async()=>{if(!await confirmAction({title:"删除自定义模板",message:"已有条目不会受影响，但这个创作蓝图将从世界库中移除。",confirmLabel:"删除模板",danger:true}))return;try{await api(`/api/templates/${encodeURIComponent(button.dataset.deleteTemplate)}`,{method:"DELETE"});toast("模板已删除");await renderTemplates();}catch(error){toast(error.message,"error");}}));
}

function templateCard(template) {
  return `<article class="template-card"><div class="template-icon ${template.type}">${escapeHtml((TYPE_LABELS[template.type]||template.type).slice(0,1))}</div><div><span class="eyebrow">${template.builtin?"SYSTEM":"CUSTOM"} · ${TYPE_LABELS[template.type]||template.type}</span><h3>${escapeHtml(template.name)}</h3><p>${escapeHtml(template.description||"自定义内容结构")}</p><div class="template-tags">${(template.tags||[]).map(tag=>`<span>${escapeHtml(tag)}</span>`).join("")}</div></div><footer><a class="button primary small" href="#/new?template=${encodeURIComponent(template.id)}">使用模板</a>${template.builtin?"":`<button class="button danger small" data-delete-template="${escapeHtml(template.id)}">删除</button>`}</footer></article>`;
}

async function renderRelations() {
  const graph = await api("/api/graph");
  const nodes = new Map(graph.nodes.map(node=>[node.id,node]));
  const semantic = graph.edges.filter(edge=>edge.kind==="relation");
  const linked = new Set(graph.edges.flatMap(edge=>[edge.source,edge.target]));
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">KNOWLEDGE GRAPH / 05</span><h1>关系网络</h1><p>从语义关系与 Wiki 提及两个层次观察知识结构。</p></div><a class="button primary" href="#/new">＋ 新建关联条目</a></div>
    <section class="network-metrics"><div><strong>${graph.nodes.length}</strong><span>可见节点</span></div><div><strong>${semantic.length}</strong><span>语义关系</span></div><div><strong>${graph.edges.length-semantic.length}</strong><span>正文提及</span></div><div><strong>${linked.size}</strong><span>已连接条目</span></div></section>
    <section class="network-layout"><div class="panel network-panel"><div class="panel-header"><div><span class="eyebrow">MAP</span><h2>知识网络概览</h2></div><span class="network-legend"><i></i>语义关系 <i></i>正文提及</span></div>${networkSvg(graph)}</div>
    <div class="panel"><div class="panel-header"><div><span class="eyebrow">RELATIONS</span><h2>结构化关系</h2></div></div><div class="relation-ledger">${semantic.slice(0,50).map(edge=>{const source=nodes.get(edge.source),target=nodes.get(edge.target);return `<div><a href="#/entry/${edge.source}">${escapeHtml(source?.title||edge.source)}</a><span>${escapeHtml(RELATION_LABELS[edge.label]||edge.label)} →</span><a href="#/entry/${edge.target}">${escapeHtml(target?.title||edge.target)}</a></div>`;}).join("")||"<p class='muted'>还没有结构化关系。编辑条目即可建立关系。</p>"}</div></div></section>`;
}

function networkSvg(graph) {
  const visible=graph.nodes.slice(0,32);if(!visible.length)return emptySmall("创建条目后，关系网络会显示在这里。");
  const ids=new Set(visible.map(node=>node.id));const width=920,height=440,cx=width/2,cy=height/2;
  const points=new Map(visible.map((node,index)=>{const angle=(Math.PI*2*index/visible.length)-Math.PI/2;const ring=index%3;const radius=90+ring*62;return[node.id,{x:cx+Math.cos(angle)*radius,y:cy+Math.sin(angle)*radius,node}];}));
  const lines=graph.edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target)).slice(0,100).map(edge=>{const a=points.get(edge.source),b=points.get(edge.target);return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="${edge.kind}"/>`;}).join("");
  const nodeMarkup=[...points.values()].map(point=>`<a href="#/entry/${point.node.id}"><circle cx="${point.x}" cy="${point.y}" r="18" class="node ${point.node.type}"/><text x="${point.x}" y="${point.y+34}">${escapeHtml(point.node.title.length>7?point.node.title.slice(0,7)+"…":point.node.title)}</text></a>`).join("");
  return `<div class="network-canvas"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="世界库关系网络">${lines}${nodeMarkup}</svg></div>`;
}

async function renderTimeline() {
  const items = await api("/api/timeline");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">CHRONOLOGY / 04</span><h1>时间线</h1><p>按内部序号排序，同时保留世界内历法的原始表达。</p></div></div>${items.length ? `<div class="timeline">${items.map(item=>`<article class="timeline-item"><span class="eyebrow">${escapeHtml(item.time.display || "未命名时间")} · ${item.time.earliest_ordinal ?? "?"}${item.time.latest_ordinal !== item.time.earliest_ordinal ? `—${item.time.latest_ordinal ?? "?"}`:""}</span><h3><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></h3><span class="muted">${TYPE_LABELS[item.type] || item.type} · ${STATUS_LABELS[item.status] || item.status}</span></article>`).join("")}</div>` : emptySmall("当前没有带时间信息的条目。")}`;
}
function timelineLine(item) { return `<p><span class="eyebrow">${escapeHtml(item.time.display || item.time.earliest_ordinal || "未定")}</span><br><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></p>`; }

async function renderChecks() {
  const checks = await api("/api/checks");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">QUALITY CENTER / 06</span><h1>质量中心</h1><p>系统只列出证据与定位，不自动改写内容。</p></div><button id="run-reindex" class="button">重新扫描</button></div>
    ${checks.length ? `<div class="check-list">${checks.map(item=>`<article class="check ${item.severity}"><span></span><div><h3>${escapeHtml(item.message)}</h3><p>${escapeHtml(item.rule_id)} · ${escapeHtml(item.entry_title || item.entry_id || "世界库")}</p></div>${item.entry_id ? `<a class="button small" href="#/entry/${item.entry_id}">查看</a>`:""}</article>`).join("")}</div>` : `<div class="empty success-text"><h2>未发现一致性问题</h2><p>当前索引与规则检查均已完成。</p></div>`}`;
  document.querySelector("#run-reindex").addEventListener("click", async event => { setBusy(event.currentTarget,true); try { await api("/api/reindex",{method:"POST"}); toast("扫描完成"); await renderChecks(); } catch(error){toast(error.message,"error");} });
}

async function renderTransfer() {
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">PORTABILITY / 07</span><h1>迁移与发布</h1><p>传输包用于继续编辑，审阅包用于独立只读浏览。</p></div></div>
    <div class="grid-2"><section class="panel"><h2>导出世界传输包</h2><p>包含当前世界库的 Markdown、关系、地图与附件，并带逐文件 SHA-256。</p><button id="export-vault" class="button primary">下载 .worldvault</button></section>
    <section class="panel"><h2>导出静态审阅包</h2><p>生成无需安装本程序即可打开的只读 HTML 快照。</p><button id="export-review" class="button">下载审阅包</button></section>
    <section class="panel"><h2>合并传输包</h2><p>先预览新增、相同和冲突条目。默认保留本地版本。</p><form id="merge-import-form"><div class="field"><input name="file" type="file" accept=".worldvault,.zip" required></div><div class="actions"><button class="button">检查传输包</button></div></form></section>
    <section class="panel"><h2>世界库位置</h2><p class="mono">${escapeHtml(state.info.active_vault)}</p><p class="muted">索引、日志和密钥不会写入此传输包。</p></section></div><div id="import-preview"></div>`;
  document.querySelector("#export-vault").addEventListener("click", event => exportFile(event, "/api/export/worldvault", {scope:"vault",world_ids:[]}));
  document.querySelector("#export-review").addEventListener("click", event => exportFile(event, "/api/export/review", {}));
  document.querySelector("#merge-import-form").addEventListener("submit", event => importFile(event,"merge"));
}

async function exportFile(event, path, payload) {
  const button = event.currentTarget; setBusy(button,true,"生成中……");
  try { const response = await api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); await downloadResponse(response); toast("导出已生成并开始下载"); }
  catch(error){toast(error.message,"error");} finally {setBusy(button,false);}
}

async function importFile(event, mode) {
  event.preventDefault(); const button=event.submitter; setBusy(button,true,"检查中……");
  const form = new FormData(event.currentTarget); const file = form.get("file"); const name = form.get("name") || "导入的世界库";
  try { const preview = await api(`/api/import/preview?mode=${mode}&new_vault_name=${encodeURIComponent(name)}`,{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file}); showImportPreview(preview, mode); }
  catch(error){toast(error.message,"error");} finally {setBusy(button,false);}
}

function showImportPreview(preview, mode) {
  const root = document.querySelector("#import-preview") || content;
  const conflictRows = preview.conflicts.map(item=>`<div class="relation-row" data-conflict="${item.id}"><span><strong>${escapeHtml(item.title)}</strong><br><small>${escapeHtml(item.id)}</small></span><select><option value="local">保留本地</option><option value="incoming">采用导入版本</option><option value="draft">另存为草稿副本</option></select></div>`).join("");
  const fileRows = (preview.file_conflicts || []).map(item=>`<div class="relation-row" data-file-conflict="${escapeHtml(item.path)}"><span><strong>${escapeHtml(item.path)}</strong><br><small>${item.bytes} bytes</small></span><select><option value="local">保留本地文件</option><option value="incoming">采用导入文件</option></select></div>`).join("");
  root.innerHTML = `<section class="panel" style="margin-top:22px"><h2>导入预览</h2><div class="stat-grid"><div class="stat"><strong>${preview.incoming_entries}</strong><span>传入条目</span></div><div class="stat"><strong>${preview.additions.length}</strong><span>新增</span></div><div class="stat"><strong>${preview.identical.length}</strong><span>相同</span></div><div class="stat"><strong>${preview.conflicts.length + (preview.file_conflicts || []).length}</strong><span>冲突</span></div></div>${conflictRows ? `<h3>逐项处理条目冲突</h3>${conflictRows}`:"<p class='success-text'>没有条目冲突。</p>"}${fileRows ? `<h3>逐项处理附件或世界配置冲突</h3>${fileRows}`:""}<div class="actions"><button id="commit-import" class="button primary">确认导入</button><button id="cancel-import" class="button">取消</button></div></section>`;
  document.querySelector("#cancel-import").addEventListener("click",()=>{ if(mode==="new") router(); else root.innerHTML=""; });
  document.querySelector("#commit-import").addEventListener("click", async event => { const button=event.currentTarget; setBusy(button,true,"导入中……"); const choices={}; document.querySelectorAll("[data-conflict]").forEach(row=>choices[row.dataset.conflict]=row.querySelector("select").value);
    document.querySelectorAll("[data-file-conflict]").forEach(row=>choices[`file:${row.dataset.fileConflict}`]=row.querySelector("select").value);
    try { await api(`/api/import/${preview.token}/commit`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conflict_choices:choices})}); toast("导入完成"); location.hash="#/"; await router(); }
    catch(error){toast(error.message,"error");setBusy(button,false);} });
}

async function renderSettings() {
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">PLATFORM / 08</span><h1>平台设置</h1><p>管理当前世界库、索引、存储位置和本地程序。</p></div></div>
    <div class="grid-2"><section class="panel"><h2>当前世界库</h2><p><strong>${escapeHtml(state.info.vault.name)}</strong></p><p class="mono">${escapeHtml(state.info.active_vault)}</p><p>${state.info.worlds.map(w=>escapeHtml(w.name)).join("、")}</p><div class="actions"><button id="reindex" class="button">重建索引</button><button id="close-vault" class="button danger">关闭世界库</button></div></section>
    <section class="panel"><h2>创建另一个世界</h2><form id="create-world-form"><div class="field"><label>世界名称</label><input name="name" required placeholder="例如：镜海宇宙"></div><div class="actions"><button class="button">创建世界</button></div></form><p class="muted">当前世界：${state.info.worlds.map(w=>escapeHtml(w.name)).join("、")}</p></section>
    <section class="panel"><h2>打开其他世界库</h2><form id="settings-open-form"><div class="field"><label>世界库完整路径</label><input name="path" required placeholder="包含 vault.yaml 的目录"></div><div class="actions"><button class="button">打开</button></div></form></section>
    <section class="panel"><h2>近期世界库</h2><ul class="context-list">${state.info.recent_vaults.map(path=>`<li><button class="button small recent-vault" data-path="${escapeHtml(path)}">${escapeHtml(path)}</button></li>`).join("")}</ul></section>
    <section class="panel"><h2>危险操作</h2><p>永久删除当前世界库的 Markdown 正文、地图和附件，同时清理可重建索引。此操作不会保留隐藏副本。</p><p>建议先在“迁移与发布”中导出 <code>.worldvault</code>。</p><div class="actions"><button id="delete-vault" class="button danger">永久删除当前世界库</button></div></section>
    <section class="panel"><h2>隐私边界</h2><p>应用只监听 <code>127.0.0.1</code>。外部 AI 默认未启用，世界传输包不包含索引、日志或凭据。</p><div class="actions"><button id="exit-app" class="button danger">退出本地程序</button></div></section></div>`;
  document.querySelector("#settings-open-form").addEventListener("submit",openVault);
  document.querySelector("#create-world-form").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;setBusy(button,true);try{await api("/api/worlds",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:new FormData(event.currentTarget).get("name")})});toast("新世界已创建");await router();}catch(e){toast(e.message,"error");}finally{setBusy(button,false);}});
  document.querySelector("#reindex").addEventListener("click",async event=>{setBusy(event.currentTarget,true);try{const r=await api("/api/reindex",{method:"POST"});toast(`已索引 ${r.entries} 个条目`);}catch(e){toast(e.message,"error");}finally{setBusy(event.currentTarget,false);}});
  document.querySelector("#close-vault").addEventListener("click",async()=>{if(!await confirmAction({title:"关闭当前世界库",message:"应用只会断开当前目录，不会删除任何文件。",confirmLabel:"关闭世界库"}))return;await api("/api/vaults/close",{method:"POST"});location.hash="#/";await router();});
  document.querySelector("#delete-vault").addEventListener("click",async event=>{
    const vaultName=String(state.info.vault.name||"");
    if(!await confirmAction({title:"永久删除世界库",message:"将删除 Markdown 正文、地图、附件和可重建索引。此操作不可撤销，也不会保留隐藏副本。",confirmLabel:"永久删除",expectedText:vaultName,danger:true}))return;
    const button=event.currentTarget;setBusy(button,true,"删除中……");
    try{await api("/api/vaults/current",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmation:vaultName})});location.hash="#/";await router();toast("世界库已永久删除");}
    catch(error){toast(error.message,"error");setBusy(button,false);}
  });
  document.querySelector("#exit-app").addEventListener("click",async()=>{if(!await confirmAction({title:"退出本地程序",message:"退出后浏览器页面将停止工作；已保存的世界库内容不会受影响。",confirmLabel:"退出程序"}))return;const result=await api("/api/application/exit",{method:"POST"});content.innerHTML=`<div class="empty"><h2>Worldbuilding Wiki 已退出</h2><p>现在可以关闭此浏览器页面。</p></div>`;if(!result.accepted)toast("当前开发运行方式不支持从页面退出");});
  document.querySelectorAll(".recent-vault").forEach(button=>button.addEventListener("click",async()=>{try{await api("/api/vaults/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:button.dataset.path})});location.hash="#/";await router();}catch(e){toast(e.message,"error");}}));
}

function renderStartupError(error) {
  content.innerHTML = `<div class="empty"><h2>应用初始化失败</h2><p>${escapeHtml(error?.message || "未知错误")}</p><button class="button" onclick="location.reload()">重新加载</button></div>`;
  toast(error?.message || "应用初始化失败", "error");
}

document.querySelector("#global-search").addEventListener("submit", event => { event.preventDefault(); const q=document.querySelector("#search-input").value.trim(); location.hash=`#/entries?q=${encodeURIComponent(q)}`; });
document.querySelector("#menu-button").addEventListener("click",()=>document.body.classList.toggle("menu-open"));
document.querySelector("#sidebar-scrim").addEventListener("click",()=>document.body.classList.remove("menu-open"));
document.addEventListener("keydown", event => {
  const target = event.target;
  const isEditing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
  if (event.key === "/" && !isEditing && state.info?.ready) {
    event.preventDefault();
    document.querySelector("#search-input").focus();
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && state.info?.ready) {
    event.preventDefault();
    document.querySelector("#search-input").focus();
  }
});
document.querySelectorAll("[data-nav]").forEach(link => link.addEventListener("click", event => {
  if (link.getAttribute("aria-disabled") !== "true") return;
  event.preventDefault();
  toast("请先创建、打开或导入一个世界库", "error");
  document.querySelector("#create-vault-form input")?.focus();
}));
window.addEventListener("hashchange", () => router().catch(renderStartupError));
router().catch(renderStartupError);
