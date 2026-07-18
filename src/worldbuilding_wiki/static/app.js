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
    if (parts[0] === "history" && parts[1]) return renderHistory(parts[1]);
    if (parts[0] === "entry" && parts[1]) return renderEntry(parts[1]);
    if (parts[0] === "edit" && parts[1]) return renderEditor(parts[1]);
    if (parts[0] === "new") return renderEditor(null, params.get("template"));
    if (parts[0] === "templates") return renderTemplates();
    if (parts[0] === "timeline") return renderTimeline();
    if (parts[0] === "relations") return renderRelations();
    if (parts[0] === "maps") return renderMaps(parts[1] || "");
    if (parts[0] === "checks") return renderChecks();
    if (parts[0] === "suggestions") return renderSuggestions();
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
    <div class="hero"><span class="eyebrow">LOCAL WORLDBUILDING</span>
      <h1>把一个世界，慢慢写活。</h1>
      <p>本地 Markdown，随时可迁移。</p>
    </div>
    <div class="welcome-grid">
      <div class="welcome-option featured"><span class="option-icon">✦</span><h2>新建世界库</h2><p class="muted">立即开始，内置完整示例可随时删除。</p>
        <form id="create-vault-form"><input name="name" required placeholder="世界库名称"><input name="world_name" required value="主世界" placeholder="第一个世界名称"><label class="check-option"><input name="include_sample" type="checkbox" checked><span><b>载入示例全套数据</b><small>13 条设定、关系、时间线与地图</small></span></label><button class="button primary">创建并打开</button></form></div>
      <div class="welcome-option"><span class="option-icon">↗</span><h2>打开目录</h2><p class="muted">继续已有的本地世界库。</p>
        <form id="open-vault-form"><input name="path" required placeholder="世界库完整路径"><button class="button">打开目录</button></form></div>
      <div class="welcome-option"><span class="option-icon">⇩</span><h2>导入传输包</h2><p class="muted">从 <code>.worldvault</code> 继续创作。</p>
        <form id="welcome-import-form"><input name="name" required value="导入的世界库"><input name="file" type="file" accept=".worldvault,.zip" required><button class="button">检查并导入</button></form></div>
    </div></section>`;
  document.querySelector("#create-vault-form").addEventListener("submit", createVault);
  document.querySelector("#open-vault-form").addEventListener("submit", openVault);
  document.querySelector("#welcome-import-form").addEventListener("submit", event => importFile(event, "new"));
}

async function createVault(event) {
  event.preventDefault(); const button = event.submitter; setBusy(button, true);
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.include_sample = event.currentTarget.elements.include_sample.checked;
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
  const [dashboard, sample] = await Promise.all([api("/api/dashboard"), api("/api/sample")]);
  const summary = dashboard.summary;
  const checkTotal = Object.values(dashboard.checks).reduce((sum, value) => sum + value, 0);
  const sampleReady = sample.state === "complete";
  const samplePartial = sample.state === "partial";
  content.innerHTML = `<section class="workspace-hero"><div class="hero-copy"><span class="eyebrow">${sampleReady ? "示例全套数据 · 已就绪" : "LOCAL CREATIVE VAULT"}</span><h1>${escapeHtml(state.info.vault.name)}</h1>
      <p>${summary.entries ? `${summary.entries} 条设定正在生长。` : "从第一条设定开始。"}</p>
      <div class="hero-actions"><a class="button primary" href="#/new">＋ 新建条目</a><a class="button glass" href="#/entries">浏览全部</a></div></div>
      <a class="hero-map" href="${sampleReady ? `#/maps/${sample.map_id}` : "#/maps"}" aria-label="打开地图"><span>探索地图</span></a></section>
    <section class="metric-grid">
      ${metricCard(summary.entries, "全部条目", "世界规模", "accent")}
      ${metricCard(`${summary.entries ? Math.round(summary.canonical * 100 / summary.entries) : 0}%`, "正史比例", `${summary.canonical} 条已确认`, "success")}
      ${metricCard(summary.drafts, "草稿", "等待推进", summary.drafts ? "warning" : "success")}
      ${metricCard(summary.relations + summary.links, "连接", "关系与引用", "accent")}
    </section>
    <section class="dashboard-grid">
      <div class="panel span-2 recent-panel"><div class="panel-header"><div><span class="eyebrow">RECENT</span><h2>最近编辑</h2></div><a href="#/entries">查看全部 →</a></div>${managementRows(dashboard.recent.slice(0,6), false)}</div>
      <div class="panel sample-panel ${sampleReady ? "installed" : ""}"><div class="sample-orbit"><i></i><i></i><i></i></div><span class="eyebrow">BUILT-IN SHOWCASE</span><h2>示例全套数据</h2><strong>${sample.entries} / ${sample.total_entries}</strong><p>${sampleReady ? "设定、人物、事件、关系与地图均可直接体验。" : samplePartial ? "示例不完整，可一键恢复标准版本。" : "载入完整世界，快速查看实际效果。"}</p><div class="sample-actions">${sampleReady ? `<a class="button small" href="#/entry/concept_5a0000000001">打开示例</a><button id="restore-sample" class="button small">还原</button><button id="delete-sample" class="button danger small">删除</button>` : `<button id="restore-sample" class="button primary">${samplePartial ? "还原完整示例" : "载入示例"}</button>`}</div></div>
      <div class="panel quick-panel"><div class="panel-header"><div><span class="eyebrow">QUICK START</span><h2>快捷入口</h2></div></div><div class="quick-grid"><a href="#/templates"><i>▤</i><span>从模板新建</span></a><a href="#/timeline"><i>◷</i><span>查看时间线</span></a><a href="#/relations"><i>⌘</i><span>探索关系</span></a><a href="#/checks"><i>✓</i><span>${checkTotal} 项检查</span></a></div></div>
      <div class="panel"><div class="panel-header"><div><span class="eyebrow">OVERVIEW</span><h2>内容构成</h2></div></div>${distributionBars(dashboard.by_type, TYPE_LABELS)}</div>
    </section>`;
  document.querySelector("#restore-sample")?.addEventListener("click", restoreSample);
  document.querySelector("#delete-sample")?.addEventListener("click", deleteSample);
}

async function restoreSample(event) {
  const button = event.currentTarget; setBusy(button, true, "还原中……");
  try {
    const result = await api("/api/sample/restore", {method:"POST"});
    toast(`示例已就绪：${result.entries} 条内容`);
    await refreshInfo(); await renderHome();
  } catch (error) { toast(error.message, "error"); } finally { setBusy(button, false); }
}

async function deleteSample(event) {
  if (!await confirmAction({title:"删除示例全套数据",message:"只会移除带有示例标记的内容；你后来创建的条目不会受影响。",confirmLabel:"删除示例",danger:true})) return;
  const button = event.currentTarget; setBusy(button, true, "删除中……");
  try {
    const result = await api("/api/sample", {method:"DELETE"});
    toast(`已删除 ${result.removed_entries} 条示例内容`);
    await refreshInfo(); await renderHome();
  } catch (error) { toast(error.message, "error"); } finally { setBusy(button, false); }
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
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">LIBRARY</span><h1>全部条目</h1></div><div class="actions"><a class="button" href="#/templates">模板</a><a class="button primary" href="#/new">＋ 新建</a></div></div>
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
  content.innerHTML = `<div class="page-heading"><div><a href="#/entries">← 全部条目</a></div><div class="actions"><a class="button" href="#/history/${entry.id}">版本历史</a><a class="button" href="#/edit/${entry.id}">编辑</a><button id="archive-entry" class="button danger">标记废弃</button></div></div>
    <div class="article-layout"><article class="article"><span class="eyebrow">${TYPE_LABELS[entry.type] || entry.type} · ${STATUS_LABELS[entry.status] || entry.status}</span><h1>${escapeHtml(entry.title)}</h1>
      <div class="metadata-line"><span>${escapeHtml(entry.id)}</span><span>世界：${escapeHtml(entry.world)}</span><span>分支：${escapeHtml(entry.branch)}</span>${(entry.tags || []).map(tag=>`<span>#${escapeHtml(tag)}</span>`).join("")}</div><hr><div class="article-body">${data.rendered_html || "<p class='muted'>尚无正文。</p>"}</div></article>
      <aside class="context-column"><section class="panel"><h3>反向链接</h3><ul class="context-list">${data.backlinks.map(item=>`<li><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></li>`).join("") || "<li class='muted'>暂无</li>"}</ul></section>
      <section class="panel"><h3>提及</h3><div class="context-list">${links || "<span class='muted'>暂无</span>"}</div></section>
      <section class="panel"><h3>关系</h3><ul class="context-list">${relations || "<li class='muted'>暂无</li>"}</ul></section>
      ${entry.template ? `<section class="panel"><h3>模板字段</h3><p class="muted">${escapeHtml(entry.template.id)} · v${entry.template.version}</p><dl class="custom-field-summary">${Object.entries(entry.custom_fields||{}).map(([key,value])=>`<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(Array.isArray(value)?value.join("、"):String(value))}</dd>`).join("")||"<span class='muted'>暂无值</span>"}</dl></section>` : ""}
      <section class="panel"><h3>检查</h3><ul class="context-list">${data.checks.map(item=>`<li>${escapeHtml(item.message)}</li>`).join("") || "<li class='success-text'>没有发现问题</li>"}</ul></section></aside></div>`;
  document.querySelector("#archive-entry").addEventListener("click", async () => {
    if (!await confirmAction({title:"标记为废弃",message:"正文不会被删除，但该条目将不再作为当前有效设定。",confirmLabel:"确认标记",danger:true})) return;
    try { await api(`/api/entries/${entry.id}?expected_hash=${entry.content_hash}`, {method:"DELETE"}); toast("条目已标记为废弃"); await renderEntry(entry.id); } catch (error) { toast(error.message,"error"); }
  });
}

async function renderHistory(id) {
  const [detail, history] = await Promise.all([
    api(`/api/entries/${encodeURIComponent(id)}`),
    api(`/api/entries/${encodeURIComponent(id)}/history`),
  ]);
  const entry = detail.entry;
  const revisions = history.revisions || [];
  content.innerHTML = `<div class="page-heading"><div><a href="#/entry/${entry.id}">← 返回条目</a><span class="eyebrow">HISTORY</span><h1>${escapeHtml(entry.title)}</h1></div></div>
    ${revisions.length ? `<div class="history-layout"><aside class="panel history-sidebar"><label for="history-revision">选择历史版本</label><select id="history-revision">${revisions.map(item=>`<option value="${escapeHtml(item.revision_id)}">${formatDate(item.updated_at)} · ${escapeHtml(item.title)}</option>`).join("")}</select><div id="history-meta"></div><button id="restore-revision" class="button danger">恢复这个版本</button><small>恢复前会先保存当前版本，因此可以再次撤回。</small></aside><section class="panel history-diff"><div class="panel-header"><div><span class="eyebrow">DIFF / 历史 → 当前</span><h2>版本差异</h2></div><span id="diff-summary" class="muted"></span></div><pre id="diff-lines" class="diff-lines" aria-live="polite"></pre></section></div>` : `<div class="empty"><h2>还没有历史版本</h2><p>编辑并保存一次条目后，这里会出现修改前的快照。</p><a class="button primary" href="#/edit/${entry.id}">编辑条目</a></div>`}`;
  if (!revisions.length) return;
  const select = document.querySelector("#history-revision");
  const restore = document.querySelector("#restore-revision");
  async function loadDiff() {
    const revisionId = select.value;
    const selected = revisions.find(item=>item.revision_id===revisionId);
    restore.disabled = true;
    document.querySelector("#history-meta").innerHTML = `<dl><dt>版本时间</dt><dd>${formatDate(selected?.updated_at)}</dd><dt>状态</dt><dd>${escapeHtml(STATUS_LABELS[selected?.status] || selected?.status || "—")}</dd><dt>分支</dt><dd>${escapeHtml(selected?.branch || "main")}</dd></dl>`;
    try {
      const diff = await api(`/api/entries/${encodeURIComponent(id)}/diff?revision_id=${encodeURIComponent(revisionId)}`);
      document.querySelector("#diff-summary").textContent = `+${diff.summary.added} / −${diff.summary.deleted}`;
      document.querySelector("#diff-lines").innerHTML = diff.lines.length ? diff.lines.map(line=>`<span class="diff-${line.kind}">${escapeHtml(line.text) || " "}</span>`).join("") : `<span class="diff-context">两个版本内容一致</span>`;
    } finally {
      restore.disabled = false;
    }
  }
  select.addEventListener("change",()=>loadDiff().catch(error=>toast(error.message,"error")));
  restore.addEventListener("click",async()=>{
    const selected = revisions.find(item=>item.revision_id===select.value);
    if (!await confirmAction({title:"恢复历史版本",message:`将把“${entry.title}”恢复到 ${formatDate(selected?.updated_at)} 的内容。当前版本会先被保存。`,confirmLabel:"确认恢复",danger:true})) return;
    setBusy(restore,true,"恢复中……");
    try {
      await api(`/api/entries/${encodeURIComponent(id)}/restore`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision_id:select.value,expected_hash:history.current.content_hash})});
      toast("历史版本已恢复");
      await renderHistory(id);
    } catch (error) {
      toast(error.message,"error");
      setBusy(restore,false);
    }
  });
  await loadDiff();
}

async function renderEditor(id = null, templateId = null) {
  let entry = {type:"concept", status:"draft", title:"", aliases:[], tags:[], branch:"main", body:"", relations:[], time:null, template:null, custom_fields:{}};
  if (id) entry = (await api(`/api/entries/${id}`)).entry;
  let activeTemplate = null;
  if (!id && templateId) {
    const templates = await api("/api/templates");
    activeTemplate = templates.find(item=>item.id===templateId) || null;
    if (activeTemplate) entry = {...entry,type:activeTemplate.type,status:activeTemplate.status,tags:activeTemplate.tags,body:activeTemplate.body};
  }
  if (id && entry.template) activeTemplate = await api(`/api/templates/${encodeURIComponent(entry.template.id)}/versions/${entry.template.version}`);
  const allEntries = await api("/api/entries?limit=1000");
  const worldOptions = state.info.worlds.map(world=>`<option value="${escapeHtml(world.id)}" ${(entry.world || state.info.worlds[0].id) === world.id ? "selected" : ""}>${escapeHtml(world.name)}</option>`).join("");
  const relations = entry.relations || [];
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">${id ? "EDIT" : "CREATE"}</span><h1>${id ? "编辑条目" : "新建条目"}</h1></div></div>
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
      ${activeTemplate?.fields?.length ? `<fieldset class="custom-fields full"><legend>模板字段 · ${escapeHtml(activeTemplate.name)} v${activeTemplate.version}</legend>${activeTemplate.fields.map(field=>customFieldInput(field,entry.custom_fields?.[field.id])).join("")}</fieldset>` : ""}
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
    const payload = { title:form.get("title"), type:id ? entry.type : form.get("type"), world:id ? entry.world : form.get("world"), status:form.get("status"), aliases:splitList(form.get("aliases")), tags:splitList(form.get("tags")), branch:form.get("branch").trim() || "main", body:form.get("body"), expected_hash:entry.content_hash, template_id:id?null:activeTemplate?.id, template_version:id?null:activeTemplate?.version, custom_fields:activeTemplate?readCustomFields():null,
      relations:[...relationRoot.querySelectorAll(".relation-row")].map(row=>({predicate:row.querySelector('[data-key="predicate"]').value.trim(), object:row.querySelector('[data-key="object"]').value.trim()})).filter(item=>item.object),
      time: display || earliest || latest ? {display, earliest_ordinal:earliest === "" ? null : Number(earliest), latest_ordinal:latest === "" ? null : Number(latest), precision:"custom"} : null };
    try { const result = await api(id ? `/api/entries/${id}` : "/api/entries", {method:id?"PUT":"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); toast("条目已保存"); location.hash = `#/entry/${result.entry.id}`; }
    catch(error){ toast(error.message,"error"); } finally { setBusy(button,false); }
  });
}
function splitList(value) { return String(value || "").split(/[,，]/).map(x=>x.trim()).filter(Boolean); }

function customFieldInput(field, value) {
  const required=field.required?"required":"";const label=`${escapeHtml(field.name)}${field.required?" *":""}`;const common=`data-custom-field="${escapeHtml(field.id)}" data-field-type="${escapeHtml(field.type)}"`;
  if(field.type==="boolean")return `<label class="custom-boolean"><input type="checkbox" ${common} ${value?"checked":""}> ${label}</label>`;
  if(field.type==="select")return `<div class="field"><label>${label}</label><select ${common} ${required}><option value="">请选择</option>${field.options.map(option=>`<option value="${escapeHtml(option)}" ${value===option?"selected":""}>${escapeHtml(option)}</option>`).join("")}</select></div>`;
  const inputType=field.type==="number"?"number":"text";const display=Array.isArray(value)?value.join(", "):(value??field.default??"");return `<div class="field"><label>${label}</label><input type="${inputType}" ${common} ${required} value="${escapeHtml(display)}" ${field.type==="number"?'step="any"':""}></div>`;
}

function readCustomFields() {
  const result={};document.querySelectorAll("[data-custom-field]").forEach(input=>{let value;if(input.dataset.fieldType==="boolean")value=input.checked;else if(input.dataset.fieldType==="number")value=input.value===""?"":Number(input.value);else if(input.dataset.fieldType==="list")value=splitList(input.value);else value=input.value;result[input.dataset.customField]=value;});return result;
}

async function renderTemplates() {
  const [templates, entries] = await Promise.all([api("/api/templates"),api("/api/entries?limit=200")]);
  const builtin = templates.filter(item=>item.builtin); const custom = templates.filter(item=>!item.builtin);
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">BLUEPRINTS</span><h1>模板</h1></div><div class="actions"><button id="toggle-migration" class="button">迁移</button><button id="toggle-template-form" class="button primary">＋ 新建</button></div></div>
    <section id="template-form-panel" class="form-card template-builder" hidden><div class="panel-header"><div><span class="eyebrow">CUSTOM BLUEPRINT</span><h2>创建自定义模板</h2></div></div><form id="template-form" class="form-grid">
      <div class="field"><label>模板名称</label><input name="name" required maxlength="100" placeholder="例如：王国档案"></div><div class="field"><label>默认类型</label><select name="type">${typeOptions()}</select></div><div class="field"><label>默认状态</label><select name="status">${statusOptions("draft")}</select></div>
      <div class="field full"><label>用途说明</label><input name="description" maxlength="300" placeholder="告诉未来的自己何时使用它"></div><div class="field full"><label>默认标签</label><input name="tags" placeholder="用逗号分隔"></div>
      <div class="field full"><label>自定义字段</label><div id="template-fields"></div><button type="button" id="add-template-field" class="button small">＋ 添加字段</button><small>字段 ID 创建后应保持稳定；选择字段的选项用逗号分隔。</small></div>
      <div class="field full"><label>正文骨架</label><textarea name="body" placeholder="## 概述\n\n## 核心内容"></textarea></div><div class="actions full"><button class="button primary">保存模板</button><button type="button" id="cancel-template" class="button">取消</button></div></form></section>
    <section id="template-migration-panel" class="form-card" hidden><div class="panel-header"><div><span class="eyebrow">SCHEMA MIGRATION</span><h2>跨模板迁移</h2></div></div><div class="migration-layout"><div><h3>1. 选择条目</h3><div class="migration-entries">${entries.map(item=>`<label><input type="checkbox" data-migrate-entry="${escapeHtml(item.id)}"> ${escapeHtml(item.title)} <small>${escapeHtml(item.id)}</small></label>`).join("")||"<p class='muted'>暂无条目</p>"}</div></div><div><h3>2. 目标模板与字段映射</h3><label class="field"><span>目标模板</span><select id="migration-target"><option value="">请选择</option>${templates.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} · v${item.version}</option>`).join("")}</select></label><div id="migration-mapping"></div><div class="actions"><button id="preview-migration" class="button">预览迁移</button><button id="apply-migration" class="button primary" disabled>确认应用</button></div><div id="migration-preview" class="migration-preview"></div></div></div></section>
    <section class="template-section"><div class="section-heading"><div><span class="eyebrow">CURATED</span><h2>内置创作框架</h2></div><span>${builtin.length} 个模板</span></div><div class="template-grid">${builtin.map(templateCard).join("")}</div></section>
    <section class="template-section"><div class="section-heading"><div><span class="eyebrow">YOUR SYSTEM</span><h2>世界库模板</h2></div><span>${custom.length} 个模板</span></div>${custom.length?`<div class="template-grid">${custom.map(templateCard).join("")}</div>`:emptySmall("还没有自定义模板。将你反复使用的提纲保存下来，下次可直接开始写作。")}</section>`;
  const panel=document.querySelector("#template-form-panel");
  const form=document.querySelector("#template-form"),fieldRoot=document.querySelector("#template-fields");
  function openTemplateForm(template=null){form.reset();fieldRoot.innerHTML="";delete form.dataset.templateId;delete form.dataset.version;panel.querySelector("h2").textContent=template?`升级模板 · v${template.version} → v${template.version+1}`:"创建自定义模板";if(template){form.dataset.templateId=template.id;form.dataset.version=template.version;for(const key of ["name","description","type","status","body"])form.elements[key].value=template[key]||"";form.elements.tags.value=(template.tags||[]).join(", ");template.fields.forEach(field=>addTemplateFieldRow(fieldRoot,field));}panel.hidden=false;panel.scrollIntoView({behavior:"smooth"});panel.querySelector("input").focus();}
  document.querySelector("#toggle-template-form").addEventListener("click",()=>panel.hidden?openTemplateForm():panel.hidden=true);
  document.querySelector("#cancel-template").addEventListener("click",()=>panel.hidden=true);
  document.querySelector("#add-template-field").addEventListener("click",()=>addTemplateFieldRow(fieldRoot));
  form.addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;setBusy(button,true,"保存中……");const values=new FormData(event.currentTarget);const payload={name:values.get("name"),description:values.get("description"),type:values.get("type"),status:values.get("status"),tags:splitList(values.get("tags")),body:values.get("body"),fields:readTemplateFields(fieldRoot),expected_version:form.dataset.version?Number(form.dataset.version):null};try{await api(form.dataset.templateId?`/api/templates/${encodeURIComponent(form.dataset.templateId)}`:"/api/templates",{method:form.dataset.templateId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});toast(form.dataset.templateId?"模板已升级并保留旧版本":"模板已保存到世界库");await renderTemplates();}catch(error){toast(error.message,"error");}finally{setBusy(button,false);}});
  document.querySelectorAll("[data-edit-template]").forEach(button=>button.addEventListener("click",()=>openTemplateForm(custom.find(item=>item.id===button.dataset.editTemplate))));
  document.querySelectorAll("[data-delete-template]").forEach(button=>button.addEventListener("click",async()=>{if(!await confirmAction({title:"删除自定义模板",message:"已有条目不会受影响，但这个创作蓝图将从世界库中移除。",confirmLabel:"删除模板",danger:true}))return;try{await api(`/api/templates/${encodeURIComponent(button.dataset.deleteTemplate)}`,{method:"DELETE"});toast("模板已删除");await renderTemplates();}catch(error){toast(error.message,"error");}}));
  const migrationPanel=document.querySelector("#template-migration-panel"),target=document.querySelector("#migration-target"),applyButton=document.querySelector("#apply-migration");let migrationPayload=null;
  document.querySelector("#toggle-migration").addEventListener("click",()=>{migrationPanel.hidden=!migrationPanel.hidden;if(!migrationPanel.hidden)migrationPanel.scrollIntoView({behavior:"smooth"});});
  target.addEventListener("change",()=>{const template=templates.find(item=>item.id===target.value);document.querySelector("#migration-mapping").innerHTML=template?.fields?.length?`<p class="muted">为每个目标字段填写原字段 ID；留空时尝试同名 ID 或默认值。</p>${template.fields.map(field=>`<label class="field"><span>${escapeHtml(field.name)} <code>${escapeHtml(field.id)}</code></span><input data-map-target="${escapeHtml(field.id)}" placeholder="来源字段 ID"></label>`).join("")}`:"<p class='muted'>目标模板没有自定义字段。</p>";applyButton.disabled=true;});
  function migrationRequest(){const entry_ids=[...document.querySelectorAll("[data-migrate-entry]:checked")].map(item=>item.dataset.migrateEntry);const field_mapping={};document.querySelectorAll("[data-map-target]").forEach(input=>{if(input.value.trim())field_mapping[input.value.trim()]=input.dataset.mapTarget;});return{entry_ids,target_template_id:target.value,field_mapping};}
  document.querySelector("#preview-migration").addEventListener("click",async()=>{migrationPayload=migrationRequest();if(!migrationPayload.entry_ids.length||!migrationPayload.target_template_id)return toast("请选择条目和目标模板","error");try{const preview=await api("/api/templates/migration/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(migrationPayload)});document.querySelector("#migration-preview").innerHTML=`<strong>${preview.entries.length} 个条目</strong>${preview.entries.map(item=>`<p>${escapeHtml(item.title)}：${item.warnings.map(escapeHtml).join("；")||"可以迁移"}</p>`).join("")}`;applyButton.disabled=!preview.can_apply;}catch(error){toast(error.message,"error");applyButton.disabled=true;}});
  applyButton.addEventListener("click",async()=>{if(!migrationPayload)return;setBusy(applyButton,true,"迁移中……");try{const result=await api("/api/templates/migration/apply",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(migrationPayload)});toast(`已迁移 ${result.migrated} 个条目`);await renderTemplates();}catch(error){toast(error.message,"error");setBusy(applyButton,false);}});
}

function templateCard(template) {
  return `<article class="template-card"><div class="template-icon ${template.type}">${escapeHtml((TYPE_LABELS[template.type]||template.type).slice(0,1))}</div><div><span class="eyebrow">${template.builtin?"SYSTEM":"CUSTOM"} · ${TYPE_LABELS[template.type]||template.type} · v${template.version}</span><h3>${escapeHtml(template.name)}</h3><p>${escapeHtml(template.description||"自定义内容结构")}</p><div class="template-tags">${(template.fields||[]).map(field=>`<span>${escapeHtml(field.name)} · ${escapeHtml(field.type)}</span>`).join("")||(template.tags||[]).map(tag=>`<span>${escapeHtml(tag)}</span>`).join("")}</div></div><footer><a class="button primary small" href="#/new?template=${encodeURIComponent(template.id)}">使用模板</a>${template.builtin?"":`<button class="button small" data-edit-template="${escapeHtml(template.id)}">升级</button><button class="button danger small" data-delete-template="${escapeHtml(template.id)}">删除</button>`}</footer></article>`;
}

function addTemplateFieldRow(root,field={}){const row=document.createElement("div");row.className="template-field-row";row.innerHTML=`<input data-key="id" required value="${escapeHtml(field.id||"")}" placeholder="字段 ID"><input data-key="name" required value="${escapeHtml(field.name||"")}" placeholder="显示名"><select data-key="type"><option value="text">文本</option><option value="number">数字</option><option value="boolean">是/否</option><option value="select">选择</option><option value="list">列表</option></select><input data-key="options" value="${escapeHtml((field.options||[]).join(", "))}" placeholder="选择项"><label><input type="checkbox" data-key="required" ${field.required?"checked":""}> 必填</label><button type="button" class="button danger small">移除</button>`;row.querySelector('[data-key="type"]').value=field.type||"text";row.querySelector("button").addEventListener("click",()=>row.remove());root.append(row);}
function readTemplateFields(root){return[...root.querySelectorAll(".template-field-row")].map(row=>({id:row.querySelector('[data-key="id"]').value.trim(),name:row.querySelector('[data-key="name"]').value.trim(),type:row.querySelector('[data-key="type"]').value,options:splitList(row.querySelector('[data-key="options"]').value),required:row.querySelector('[data-key="required"]').checked}));}

async function renderRelations() {
  const graph = await api("/api/graph");
  const nodes = new Map(graph.nodes.map(node=>[node.id,node]));
  const semantic = graph.edges.filter(edge=>edge.kind==="relation");
  const linked = new Set(graph.edges.flatMap(edge=>[edge.source,edge.target]));
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">KNOWLEDGE GRAPH</span><h1>关系</h1></div><a class="button primary" href="#/new">＋ 新建</a></div>
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

async function renderMaps(selectedId = "") {
  const [maps, allLocations] = await Promise.all([
    api("/api/maps"),
    api("/api/entries?type=location&limit=1000"),
  ]);
  const selected = maps.find(item=>item.id===selectedId) || null;
  const worldOptions = state.info.worlds.map(world=>`<option value="${escapeHtml(world.id)}">${escapeHtml(world.name)}</option>`).join("");
  const cards = maps.map(item=>`<a class="map-card ${item.id===selectedId?"active":""}" href="#/maps/${item.id}"><img src="${escapeHtml(item.image_url)}" alt=""><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(worldLabel(item.world))} · ${item.markers.length} 个标记</small></span></a>`).join("");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">ATLAS</span><h1>地图</h1></div><button id="toggle-map-form" class="button primary">＋ 添加</button></div>
    <section id="map-create-panel" class="form-card map-create" hidden><form id="map-create-form" class="form-grid"><div class="field"><label>地图名称</label><input name="name" required maxlength="100" placeholder="例如：北境总图"></div><div class="field"><label>所属世界</label><select name="world">${worldOptions}</select></div><div class="field full"><label>原始图片</label><input name="image" type="file" accept="image/png,image/jpeg,image/webp,image/gif" required></div><div class="actions full"><button class="button primary">保存地图</button></div></form></section>
    <div class="map-workspace"><aside class="panel map-library"><h2>地图集</h2>${cards || "<p class='muted'>还没有地图。添加一张原图开始标记地点。</p>"}</aside><section id="map-editor">${selected ? mapEditorMarkup(selected, allLocations) : `<div class="empty"><h2>${maps.length?"选择一张地图":"建立你的第一张地图"}</h2><p>地图坐标不会写进图片，可随时隐藏图层或移动到不同尺寸的界面。</p></div>`}</section></div>`;
  const createPanel=document.querySelector("#map-create-panel");
  document.querySelector("#toggle-map-form").addEventListener("click",()=>{createPanel.hidden=!createPanel.hidden;if(!createPanel.hidden)createPanel.querySelector("input").focus();});
  document.querySelector("#map-create-form").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;const form=new FormData(event.currentTarget);const file=form.get("image");setBusy(button,true,"上传中……");try{const result=await api(`/api/maps?world=${encodeURIComponent(form.get("world"))}&name=${encodeURIComponent(form.get("name"))}&filename=${encodeURIComponent(file.name)}`,{method:"POST",headers:{"Content-Type":file.type||"application/octet-stream"},body:file});toast("地图已添加");location.hash=`#/maps/${result.id}`;}catch(error){toast(error.message,"error");setBusy(button,false);}});
  if (!selected) return;
  bindMapEditor(selected, allLocations);
}

function mapEditorMarkup(map, allLocations) {
  const locations=allLocations.filter(item=>item.world===map.world);
  const locationLookup=new Map(locations.map(item=>[item.id,item]));
  const visibleLayers=new Set(map.layers.filter(layer=>layer.visible).map(layer=>layer.id));
  const markers=map.markers.filter(marker=>visibleLayers.has(marker.layer_id)).map(marker=>{const location=locationLookup.get(marker.location_id);return `<button class="map-marker" data-marker-id="${escapeHtml(marker.id)}" style="left:${marker.x*100}%;top:${marker.y*100}%" title="${escapeHtml(location?.title||marker.location_id)}"><i></i><span>${escapeHtml(location?.title||marker.location_id)}</span></button>`;}).join("");
  const locationOptions=locations.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)}</option>`).join("");
  const layerOptions=map.layers.map(layer=>`<option value="${escapeHtml(layer.id)}">${escapeHtml(layer.name)}</option>`).join("");
  const layerRows=map.layers.map(layer=>`<div class="map-layer-row"><label><input type="checkbox" data-layer-visible="${escapeHtml(layer.id)}" ${layer.visible?"checked":""}> ${escapeHtml(layer.name)}</label>${map.layers.length>1?`<button class="button small danger" data-delete-layer="${escapeHtml(layer.id)}">移除</button>`:""}</div>`).join("");
  return `<div class="map-editor panel"><div class="panel-header"><div><span class="eyebrow">${escapeHtml(worldLabel(map.world))}</span><h2>${escapeHtml(map.name)}</h2></div><button id="delete-map" class="button danger small">删除地图</button></div><div class="map-controls"><div class="field"><label>要标记的地点</label><select id="map-location"><option value="">选择地点</option>${locationOptions}</select></div><div class="field"><label>目标图层</label><select id="map-layer">${layerOptions}</select></div><p class="muted">选择地点后点击地图放置标记；点击已有标记可移除。</p></div><div id="map-canvas" class="map-canvas"><img src="${escapeHtml(map.image_url)}" alt="${escapeHtml(map.name)}">${markers}</div><div class="map-layer-panel"><div><h3>图层</h3>${layerRows}</div><form id="add-map-layer" class="field"><label>新图层</label><div class="inline-form"><input name="name" required maxlength="80" placeholder="例如：政治边界"><button class="button small">添加</button></div></form></div></div>`;
}

function bindMapEditor(map, allLocations) {
  async function save(changes) {
    const result=await api(`/api/maps/${encodeURIComponent(map.id)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({...changes,expected_hash:map.content_hash})});
    await renderMaps(result.id);
  }
  const canvas=document.querySelector("#map-canvas");
  canvas.addEventListener("click",event=>{if(event.target.closest(".map-marker"))return;const locationId=document.querySelector("#map-location").value;if(!locationId)return toast("请先选择要标记的地点","error");const rect=canvas.getBoundingClientRect();const marker={id:`marker-${Date.now().toString(36)}`,layer_id:document.querySelector("#map-layer").value,location_id:locationId,x:(event.clientX-rect.left)/rect.width,y:(event.clientY-rect.top)/rect.height};save({markers:[...map.markers,marker]}).catch(error=>toast(error.message,"error"));});
  document.querySelectorAll(".map-marker").forEach(button=>button.addEventListener("click",async event=>{event.stopPropagation();const marker=map.markers.find(item=>item.id===button.dataset.markerId);const location=allLocations.find(item=>item.id===marker?.location_id);if(!await confirmAction({title:"移除地图标记",message:`从地图移除“${location?.title||marker?.location_id}”标记，地点条目本身不会删除。`,confirmLabel:"移除",danger:true}))return;save({markers:map.markers.filter(item=>item.id!==button.dataset.markerId)}).catch(error=>toast(error.message,"error"));}));
  document.querySelectorAll("[data-layer-visible]").forEach(box=>box.addEventListener("change",()=>save({layers:map.layers.map(layer=>layer.id===box.dataset.layerVisible?{...layer,visible:box.checked}:layer)}).catch(error=>toast(error.message,"error"))));
  document.querySelectorAll("[data-delete-layer]").forEach(button=>button.addEventListener("click",()=>{if(map.markers.some(marker=>marker.layer_id===button.dataset.deleteLayer))return toast("请先移除该图层上的地点标记","error");save({layers:map.layers.filter(layer=>layer.id!==button.dataset.deleteLayer)}).catch(error=>toast(error.message,"error"));}));
  document.querySelector("#add-map-layer").addEventListener("submit",event=>{event.preventDefault();const name=new FormData(event.currentTarget).get("name").trim();const layer={id:`layer-${Date.now().toString(36)}`,name,visible:true};save({layers:[...map.layers,layer]}).catch(error=>toast(error.message,"error"));});
  document.querySelector("#delete-map").addEventListener("click",async()=>{if(!await confirmAction({title:"删除地图",message:"原始地图图片、图层和标记数据都会删除，地点条目不受影响。",confirmLabel:"删除地图",danger:true}))return;try{await api(`/api/maps/${encodeURIComponent(map.id)}?expected_hash=${encodeURIComponent(map.content_hash)}`,{method:"DELETE"});toast("地图已删除");location.hash="#/maps";}catch(error){toast(error.message,"error");}});
}

async function renderTimeline() {
  const [items,branches,entries]=await Promise.all([api("/api/timeline"),api("/api/branches"),api("/api/entries?limit=1000")]);
  const branchOptions=branches.map(branch=>`<option value="${escapeHtml(branch)}">${escapeHtml(branch)}</option>`).join("");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">CHRONOLOGY / 04</span><h1>时间线与分支</h1><p>按内部序号浏览事件，创建条目变体，并逐条解释分支合并动作。</p></div></div><section class="branch-tools grid-2"><form id="variant-form" class="panel"><h2>创建分支变体</h2><label class="field"><span>来源条目</span><select name="entry_id" required><option value="">请选择</option>${entries.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)} · ${escapeHtml(item.branch)}</option>`).join("")}</select></label><label class="field"><span>目标分支</span><input name="target_branch" required pattern="[a-z][a-z0-9-]{0,62}" placeholder="alternate-route"></label><button class="button">复制为变体</button></form><form id="branch-compare-form" class="panel"><h2>比较两个分支</h2><div class="grid-2"><label class="field"><span>基准分支</span><select name="base_branch">${branchOptions}</select></label><label class="field"><span>目标分支</span><input name="target_branch" required list="branch-list" placeholder="alternate-route"><datalist id="branch-list">${branchOptions}</datalist></label></div><button class="button primary">生成比较</button></form></section><section id="branch-comparison"></section><div class="section-heading"><div><span class="eyebrow">EVENT ORDER</span><h2>事件顺序</h2></div></div>${items.length ? `<div class="timeline">${items.map(item=>`<article class="timeline-item"><span class="eyebrow">${escapeHtml(item.time.display || "未命名时间")} · ${item.time.earliest_ordinal ?? "?"}${item.time.latest_ordinal !== item.time.earliest_ordinal ? `—${item.time.latest_ordinal ?? "?"}`:""}</span><h3><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></h3><span class="muted">${TYPE_LABELS[item.type] || item.type} · ${STATUS_LABELS[item.status] || item.status} · ${escapeHtml(item.branch)}</span></article>`).join("")}</div>` : emptySmall("当前没有带时间信息的条目。")}`;
  document.querySelector("#variant-form").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter,form=new FormData(event.currentTarget);setBusy(button,true,"创建中……");try{const result=await api(`/api/branches/variants/${encodeURIComponent(form.get("entry_id"))}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target_branch:form.get("target_branch")})});toast("分支变体已创建");location.hash=`#/edit/${result.entry.id}`;}catch(error){toast(error.message,"error");setBusy(button,false);}});
  document.querySelector("#branch-compare-form").addEventListener("submit",async event=>{event.preventDefault();const form=new FormData(event.currentTarget),base=form.get("base_branch"),target=form.get("target_branch").trim();try{const comparison=await api(`/api/branches/compare?base_branch=${encodeURIComponent(base)}&target_branch=${encodeURIComponent(target)}`);renderBranchComparison(comparison);}catch(error){toast(error.message,"error");}});
}
function timelineLine(item) { return `<p><span class="eyebrow">${escapeHtml(item.time.display || item.time.earliest_ordinal || "未定")}</span><br><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></p>`; }

function renderBranchComparison(comparison){const actionable=comparison.changes.filter(item=>["added","overridden"].includes(item.kind));document.querySelector("#branch-comparison").innerHTML=`<section class="panel branch-comparison"><div class="panel-header"><div><span class="eyebrow">${escapeHtml(comparison.base_branch)} ← ${escapeHtml(comparison.target_branch)}</span><h2>分支比较</h2></div><span>${comparison.summary.overridden} 覆盖 · ${comparison.summary.added} 新增 · ${comparison.summary.inherited} 继承</span></div>${comparison.conflicts.length?`<p class="danger-text">存在 ${comparison.conflicts.length} 组重复变体，需先手工整理。</p>`:""}<div class="branch-change-list">${comparison.changes.map(item=>`<div><span class="badge">${escapeHtml(item.kind)}</span><a href="#/entry/${item.target_id}">${escapeHtml(item.target_title)}</a>${["added","overridden"].includes(item.kind)?`<select data-merge-entry="${escapeHtml(item.target_id)}"><option value="keep_base">保留基准</option><option value="accept_target">采用目标</option><option value="copy_as_draft">复制为草稿</option></select>`:"<span class='success-text'>内容已同步</span>"}</div>`).join("")||"<p class='muted'>目标分支没有独立变更。</p>"}</div>${actionable.length?`<div class="actions"><button id="apply-branch-merge" class="button primary">应用所选合并决定</button></div>`:""}</section>`;const button=document.querySelector("#apply-branch-merge");if(button)button.addEventListener("click",async()=>{const decisions={};document.querySelectorAll("[data-merge-entry]").forEach(select=>decisions[select.dataset.mergeEntry]=select.value);if(!await confirmAction({title:"应用分支合并",message:"将逐条执行当前选择；采用目标会通过版本历史保留基准内容。",confirmLabel:"确认合并"}))return;setBusy(button,true,"合并中……");try{const result=await api("/api/branches/merge",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_branch:comparison.base_branch,target_branch:comparison.target_branch,decisions})});toast(`已记录 ${result.merged} 个合并动作`);await renderTimeline();}catch(error){toast(error.message,"error");setBusy(button,false);}});}

async function renderSuggestions(){const [info,entries,proposals]=await Promise.all([api("/api/ai/info"),api("/api/entries?limit=200"),api("/api/ai/proposals")]);content.innerHTML=`<div class="page-heading"><div><span class="eyebrow">OPTIONAL AI / 08</span><h1>AI 建议提案</h1><p>默认关闭。先确认发送范围，再调用所配置模型；输出不会自动写入任何条目。</p></div><span class="badge ${info.enabled?"canon":"draft"}">${info.enabled?`${escapeHtml(info.mode)} · ${escapeHtml(info.model)}`:"未启用"}</span></div><div class="suggestion-layout"><form id="suggestion-form" class="panel"><h2>新建建议请求</h2><label class="field"><span>希望模型协助什么</span><textarea name="instruction" required maxlength="2000" placeholder="例如：检查这些条目的因果矛盾，并给出修改建议"></textarea></label><div class="suggestion-entries">${entries.map(item=>`<label><input type="checkbox" data-ai-entry="${escapeHtml(item.id)}"> ${escapeHtml(item.title)} <small>${escapeHtml(item.id)}</small></label>`).join("")}</div><div class="actions"><button id="preview-ai-scope" type="button" class="button">预览发送范围</button><button id="generate-ai-proposal" class="button primary" disabled>生成提案</button></div><div id="ai-scope-preview"></div>${!info.enabled?`<p class="muted">通过环境变量配置模式、端点和模型后重启应用；密钥不会写入世界库或提案。</p>`:""}</form><section><div class="section-heading"><div><span class="eyebrow">PROPOSALS ONLY</span><h2>提案区</h2></div><span>${proposals.length} 条</span></div><div class="proposal-list">${proposals.map(proposal=>`<article class="panel"><div class="panel-header"><div><span class="eyebrow">${formatDate(proposal.created_at)} · ${escapeHtml(proposal.provider.model)}</span><h2>${escapeHtml(proposal.instruction)}</h2></div><button class="button danger small" data-delete-proposal="${escapeHtml(proposal.id)}">删除</button></div><p class="muted">上下文：${proposal.scope.map(item=>escapeHtml(item.title)).join("、")}</p><pre>${escapeHtml(proposal.content)}</pre></article>`).join("")||emptySmall("还没有 AI 提案。")}</div></section></div>`;let approvedPayload=null;function requestPayload(){return{entry_ids:[...document.querySelectorAll("[data-ai-entry]:checked")].map(item=>item.dataset.aiEntry),instruction:new FormData(document.querySelector("#suggestion-form")).get("instruction")};}document.querySelectorAll("[data-ai-entry]").forEach(box=>box.addEventListener("change",()=>{if(document.querySelectorAll("[data-ai-entry]:checked").length>20){box.checked=false;toast("一次最多选择 20 个条目","error");}approvedPayload=null;document.querySelector("#generate-ai-proposal").disabled=true;}));document.querySelector('[name="instruction"]').addEventListener("input",()=>{approvedPayload=null;document.querySelector("#generate-ai-proposal").disabled=true;});document.querySelector("#preview-ai-scope").addEventListener("click",async()=>{try{const payload=requestPayload();const preview=await api("/api/ai/scope",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});approvedPayload=payload;document.querySelector("#ai-scope-preview").innerHTML=`<div class="scope-card"><strong>将发送 ${preview.scope.length} 个条目、${preview.prompt_characters} 字</strong><p>${preview.scope.map(item=>`${escapeHtml(item.title)}（${item.body_characters} 字；${item.fields.join("、")}）`).join("<br>")}</p><small>端点：${escapeHtml(preview.provider.endpoint_origin||"未配置")}</small></div>`;document.querySelector("#generate-ai-proposal").disabled=!preview.provider.enabled;}catch(error){toast(error.message,"error");}});document.querySelector("#suggestion-form").addEventListener("submit",async event=>{event.preventDefault();if(!approvedPayload)return;const button=event.submitter;setBusy(button,true,"模型生成中……");try{await api("/api/ai/proposals",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(approvedPayload)});toast("建议已保存到提案区，正文未修改");await renderSuggestions();}catch(error){toast(error.message,"error");setBusy(button,false);}});document.querySelectorAll("[data-delete-proposal]").forEach(button=>button.addEventListener("click",async()=>{if(!await confirmAction({title:"删除 AI 提案",message:"只删除这条运行时提案，不影响世界库正文。",confirmLabel:"删除",danger:true}))return;try{await api(`/api/ai/proposals/${encodeURIComponent(button.dataset.deleteProposal)}`,{method:"DELETE"});await renderSuggestions();}catch(error){toast(error.message,"error");}}));}

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
