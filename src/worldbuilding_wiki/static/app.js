const state = { info: null, entries: [], current: null };
const content = document.querySelector("#content");

const TYPE_LABELS = {
  character: "人物", location: "地点", organization: "组织", event: "事件",
  group: "群体", culture: "文化", rule: "规则", artifact: "物件",
  concept: "概念", source: "来源",
};
const STATUS_LABELS = { canon: "正史", draft: "草稿", rumor: "传闻", deprecated: "废弃" };

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
  document.querySelectorAll("[data-nav]").forEach(link => link.classList.toggle("active", link.dataset.nav === routeName()));
  if (!state.info.ready) return renderWelcome();
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  try {
    if (!parts.length) return renderHome();
    if (parts[0] === "entries") return renderEntries(new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "");
    if (parts[0] === "entry" && parts[1]) return renderEntry(parts[1]);
    if (parts[0] === "edit" && parts[1]) return renderEditor(parts[1]);
    if (parts[0] === "new") return renderEditor();
    if (parts[0] === "timeline") return renderTimeline();
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
    <div class="hero"><span class="eyebrow">你的世界，从一条可信设定开始</span>
      <h1>建立一座不会遗失的世界。</h1>
      <p>正文保存在你选择的 Markdown 世界库中。应用索引随时可以重建，程序升级也不会带走私人设定。</p>
    </div>
    <div class="welcome-grid">
      <div class="welcome-option"><h2>新建世界库</h2><p class="muted">使用默认安全位置，也可稍后迁移。</p>
        <form id="create-vault-form"><input name="name" required placeholder="世界库名称"><input name="world_name" required value="主世界" placeholder="第一个世界名称"><button class="button primary">创建并打开</button></form></div>
      <div class="welcome-option"><h2>打开现有目录</h2><p class="muted">目录内应存在 <code>vault.yaml</code>。</p>
        <form id="open-vault-form"><input name="path" required placeholder="世界库完整路径"><button class="button">打开目录</button></form></div>
      <div class="welcome-option"><h2>导入传输包</h2><p class="muted">校验 `.worldvault` 后创建新世界库。</p>
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
  const [entries, checks, timeline] = await Promise.all([api("/api/entries?limit=8"), api("/api/checks"), api("/api/timeline")]);
  const all = await api("/api/entries?limit=1000");
  const canon = all.filter(item => item.status === "canon").length;
  const drafts = all.filter(item => item.status === "draft").length;
  content.innerHTML = `<section class="hero"><span class="eyebrow">${escapeHtml(state.info.vault.name)}</span><h1>让每条设定，都找到自己的位置。</h1>
    <p>${state.info.worlds.length} 个世界正在生长。这里汇总最近修改、未定草稿和需要你判断的一致性问题。</p>
    <div class="actions"><a class="button primary" href="#/new">＋ 写一条新设定</a><a class="button" href="#/transfer">导入或导出</a></div></section>
    <section class="stat-grid"><div class="stat"><strong>${all.length}</strong><span>全部条目</span></div><div class="stat"><strong>${canon}</strong><span>正史设定</span></div><div class="stat"><strong>${drafts}</strong><span>待确认草稿</span></div><div class="stat"><strong>${checks.length}</strong><span>一致性提示</span></div></section>
    <section class="grid-2"><div class="panel"><div class="panel-header"><h2>最近修改</h2><a href="#/entries">查看全部</a></div>${entryCards(entries)}</div>
    <div class="panel"><div class="panel-header"><h2>时间线片段</h2><a href="#/timeline">完整时间线</a></div>${timeline.slice(0,6).map(timelineLine).join("") || emptySmall("尚未给条目添加时间")}</div></section>`;
}

function entryCards(entries) {
  if (!entries.length) return emptySmall("还没有条目，从第一条设定开始吧。");
  return `<div class="entry-grid">${entries.map(entry => `<a class="entry-card" href="#/entry/${entry.id}">${badge(entry.status)}<h3>${escapeHtml(entry.title)}</h3><p>${TYPE_LABELS[entry.type] || entry.type} · ${escapeHtml((entry.tags || []).join(" / ") || "未添加标签")}</p></a>`).join("")}</div>`;
}
function emptySmall(message) { return `<div class="empty">${escapeHtml(message)}</div>`; }

async function renderEntries(initialQuery = "") {
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">Atlas</span><h1>全部条目</h1><p>按类型与正史状态浏览你的世界。</p></div><a class="button primary" href="#/new">＋ 新建条目</a></div>
    <form id="entry-filters" class="filters"><input name="q" value="${escapeHtml(initialQuery)}" placeholder="筛选条目"><select name="type"><option value="">全部类型</option>${typeOptions("")}</select><select name="status"><option value="">全部状态</option>${statusOptions("")}</select><button class="button">筛选</button></form><div id="entry-results"></div>`;
  const form = document.querySelector("#entry-filters");
  async function load() {
    const params = new URLSearchParams(new FormData(form));
    const entries = await api(`/api/entries?${params}`);
    document.querySelector("#entry-results").innerHTML = entryCards(entries);
  }
  form.addEventListener("submit", event => { event.preventDefault(); load().catch(error => toast(error.message, "error")); });
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
    if (!confirm("将此条目标记为“废弃”？正文不会被删除。")) return;
    try { await api(`/api/entries/${entry.id}?expected_hash=${entry.content_hash}`, {method:"DELETE"}); toast("条目已标记为废弃"); await renderEntry(entry.id); } catch (error) { toast(error.message,"error"); }
  });
}

async function renderEditor(id = null) {
  let entry = {type:"concept", status:"draft", title:"", aliases:[], tags:[], branch:"main", body:"", relations:[], time:null};
  if (id) entry = (await api(`/api/entries/${id}`)).entry;
  const relations = entry.relations || [];
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">${id ? "Edit" : "Create"}</span><h1>${id ? "编辑条目" : "新建设定"}</h1><p>正文支持 Markdown 和 <code>[[Wiki 链接]]</code>。</p></div></div>
    <form id="entry-form" class="form-card"><div class="form-grid">
      <div class="field full"><label>标题</label><input name="title" required maxlength="160" value="${escapeHtml(entry.title)}" autofocus></div>
      <div class="field"><label>类型</label><select name="type" ${id ? "disabled" : ""}>${typeOptions(entry.type)}</select></div>
      <div class="field"><label>内容状态</label><select name="status">${statusOptions(entry.status)}</select></div>
      <div class="field"><label>时间线分支</label><input name="branch" value="${escapeHtml(entry.branch || "main")}" placeholder="main"></div>
      <div class="field"><label>别名</label><input name="aliases" value="${escapeHtml((entry.aliases || []).join(", "))}" placeholder="用逗号分隔"></div>
      <div class="field"><label>标签</label><input name="tags" value="${escapeHtml((entry.tags || []).join(", "))}" placeholder="用逗号分隔"></div>
      <div class="field"><label>时间显示</label><input name="time_display" value="${escapeHtml(entry.time?.display || "")}" placeholder="例如：星历 312 年霜月下旬"></div>
      <div class="field"><label>排序序号范围</label><div style="display:flex;gap:8px"><input name="earliest" type="number" value="${entry.time?.earliest_ordinal ?? ""}" placeholder="最早"><input name="latest" type="number" value="${entry.time?.latest_ordinal ?? ""}" placeholder="最晚"></div></div>
      <div class="field full"><label>语义关系</label><div id="relations"></div><button type="button" id="add-relation" class="button small">＋ 添加关系</button><small>目标填写稳定条目 ID；普通提及请直接在正文中使用 Wiki 链接。</small></div>
      <div class="field full"><label>正文</label><textarea name="body" placeholder="从这个世界中最确定的一件事开始……">${escapeHtml(entry.body)}</textarea></div>
      <div class="field full"><label>图片、地图或附件</label><div style="display:flex;gap:8px;align-items:center"><input id="asset-file" type="file" accept="image/*,.pdf,.mp3,.ogg,.wav,.txt,.csv"><button type="button" id="upload-asset" class="button small">上传并插入正文</button></div><small>附件保存在当前世界的 assets 目录，并随世界传输包一起迁移。</small></div>
    </div><div class="actions"><button class="button primary">保存条目</button><a class="button" href="${id ? `#/entry/${id}` : "#/entries"}">取消</a></div></form>`;
  const relationRoot = document.querySelector("#relations");
  function addRelation(relation = {}) {
    const row = document.createElement("div"); row.className = "relation-row";
    row.innerHTML = `<input data-key="predicate" value="${escapeHtml(relation.predicate || "related_to")}" placeholder="关系，例如 member_of"><input data-key="object" value="${escapeHtml(relation.object || "")}" placeholder="目标条目 ID"><button type="button" class="button small danger">移除</button>`;
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
    const payload = { title:form.get("title"), type:id ? entry.type : form.get("type"), status:form.get("status"), aliases:splitList(form.get("aliases")), tags:splitList(form.get("tags")), branch:form.get("branch").trim() || "main", body:form.get("body"), expected_hash:entry.content_hash,
      relations:[...relationRoot.querySelectorAll(".relation-row")].map(row=>({predicate:row.querySelector('[data-key="predicate"]').value.trim(), object:row.querySelector('[data-key="object"]').value.trim()})).filter(item=>item.object),
      time: display || earliest || latest ? {display, earliest_ordinal:earliest === "" ? null : Number(earliest), latest_ordinal:latest === "" ? null : Number(latest), precision:"custom"} : null };
    try { const result = await api(id ? `/api/entries/${id}` : "/api/entries", {method:id?"PUT":"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); toast("条目已保存"); location.hash = `#/entry/${result.entry.id}`; }
    catch(error){ toast(error.message,"error"); } finally { setBusy(button,false); }
  });
}
function splitList(value) { return String(value || "").split(/[,，]/).map(x=>x.trim()).filter(Boolean); }

async function renderTimeline() {
  const items = await api("/api/timeline");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">Chronicle</span><h1>时间线</h1><p>按内部序号排序，同时保留世界内历法的原始表达。</p></div></div>${items.length ? `<div class="timeline">${items.map(item=>`<article class="timeline-item"><span class="eyebrow">${escapeHtml(item.time.display || "未命名时间")} · ${item.time.earliest_ordinal ?? "?"}${item.time.latest_ordinal !== item.time.earliest_ordinal ? `—${item.time.latest_ordinal ?? "?"}`:""}</span><h3><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></h3><span class="muted">${TYPE_LABELS[item.type] || item.type} · ${STATUS_LABELS[item.status] || item.status}</span></article>`).join("")}</div>` : emptySmall("还没有带时间信息的条目。")}`;
}
function timelineLine(item) { return `<p><span class="eyebrow">${escapeHtml(item.time.display || item.time.earliest_ordinal || "未定")}</span><br><a href="#/entry/${item.id}">${escapeHtml(item.title)}</a></p>`; }

async function renderChecks() {
  const checks = await api("/api/checks");
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">Consistency</span><h1>一致性检查</h1><p>系统只指出证据，不会替你修改正史。</p></div><button id="run-reindex" class="button">重新扫描</button></div>
    ${checks.length ? `<div class="check-list">${checks.map(item=>`<article class="check ${item.severity}"><span></span><div><h3>${escapeHtml(item.message)}</h3><p>${escapeHtml(item.rule_id)} · ${escapeHtml(item.entry_title || item.entry_id || "世界库")}</p></div>${item.entry_id ? `<a class="button small" href="#/entry/${item.entry_id}">查看</a>`:""}</article>`).join("")}</div>` : `<div class="empty success-text"><h2>没有发现一致性问题</h2><p>继续构建你的世界吧。</p></div>`}`;
  document.querySelector("#run-reindex").addEventListener("click", async event => { setBusy(event.currentTarget,true); try { await api("/api/reindex",{method:"POST"}); toast("扫描完成"); await renderChecks(); } catch(error){toast(error.message,"error");} });
}

async function renderTransfer() {
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">Portability</span><h1>迁移与审阅</h1><p>程序与私人数据分离。传输包用于继续编辑，审阅包用于只读浏览。</p></div></div>
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
  content.innerHTML = `<div class="page-heading"><div><span class="eyebrow">Settings</span><h1>设置</h1><p>世界库正文与可重建运行状态保持分离。</p></div></div>
    <div class="grid-2"><section class="panel"><h2>当前世界库</h2><p><strong>${escapeHtml(state.info.vault.name)}</strong></p><p class="mono">${escapeHtml(state.info.active_vault)}</p><p>${state.info.worlds.map(w=>escapeHtml(w.name)).join("、")}</p><div class="actions"><button id="reindex" class="button">重建索引</button><button id="close-vault" class="button danger">关闭世界库</button></div></section>
    <section class="panel"><h2>创建另一个世界</h2><form id="create-world-form"><div class="field"><label>世界名称</label><input name="name" required placeholder="例如：镜海宇宙"></div><div class="actions"><button class="button">创建世界</button></div></form><p class="muted">当前世界：${state.info.worlds.map(w=>escapeHtml(w.name)).join("、")}</p></section>
    <section class="panel"><h2>打开其他世界库</h2><form id="settings-open-form"><div class="field"><label>世界库完整路径</label><input name="path" required placeholder="包含 vault.yaml 的目录"></div><div class="actions"><button class="button">打开</button></div></form></section>
    <section class="panel"><h2>近期世界库</h2><ul class="context-list">${state.info.recent_vaults.map(path=>`<li><button class="button small recent-vault" data-path="${escapeHtml(path)}">${escapeHtml(path)}</button></li>`).join("")}</ul></section>
    <section class="panel"><h2>隐私边界</h2><p>应用只监听 <code>127.0.0.1</code>。外部 AI 默认未启用，世界传输包不包含索引、日志或凭据。</p><div class="actions"><button id="exit-app" class="button danger">退出本地程序</button></div></section></div>`;
  document.querySelector("#settings-open-form").addEventListener("submit",openVault);
  document.querySelector("#create-world-form").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;setBusy(button,true);try{await api("/api/worlds",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:new FormData(event.currentTarget).get("name")})});toast("新世界已创建");await router();}catch(e){toast(e.message,"error");}finally{setBusy(button,false);}});
  document.querySelector("#reindex").addEventListener("click",async event=>{setBusy(event.currentTarget,true);try{const r=await api("/api/reindex",{method:"POST"});toast(`已索引 ${r.entries} 个条目`);}catch(e){toast(e.message,"error");}finally{setBusy(event.currentTarget,false);}});
  document.querySelector("#close-vault").addEventListener("click",async()=>{if(!confirm("关闭只会断开应用，不会删除文件。继续？"))return;await api("/api/vaults/close",{method:"POST"});location.hash="#/";await router();});
  document.querySelector("#exit-app").addEventListener("click",async()=>{if(!confirm("退出后浏览器页面将无法继续使用。世界库内容已经保存在磁盘。"))return;const result=await api("/api/application/exit",{method:"POST"});content.innerHTML=`<div class="empty"><h2>Worldbuilding Wiki 已退出</h2><p>现在可以关闭此浏览器页面。</p></div>`;if(!result.accepted)toast("当前开发运行方式不支持从页面退出");});
  document.querySelectorAll(".recent-vault").forEach(button=>button.addEventListener("click",async()=>{try{await api("/api/vaults/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:button.dataset.path})});location.hash="#/";await router();}catch(e){toast(e.message,"error");}}));
}

document.querySelector("#global-search").addEventListener("submit", event => { event.preventDefault(); const q=document.querySelector("#search-input").value.trim(); location.hash=`#/entries?q=${encodeURIComponent(q)}`; });
document.querySelector("#menu-button").addEventListener("click",()=>document.body.classList.toggle("menu-open"));
window.addEventListener("hashchange",router);
router();
