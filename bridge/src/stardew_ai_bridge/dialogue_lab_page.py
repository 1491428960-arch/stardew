from __future__ import annotations

import re


DIALOGUE_LAB_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stardew AI NPC · 对话实验室</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
      --ink:#33281f; --muted:#79695c; --line:#ddc9b3; --paper:#fffaf3; --strong:#fffdf9;
      --accent:#9b5b42; --accent-dark:#6e3c2e; --accent-soft:#f3dfd0; --npc:#f7e9d7; --player:#e8eff5; --good:#52745a; --warn:#946b2f; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; overflow:hidden; background: #f2e8dc; color: var(--ink); }
    button,input,select,textarea { font: inherit; }
    button { border: 1px solid var(--accent-dark); border-radius: 9px; background: var(--accent); color: #fff; cursor: pointer; padding: 9px 13px; }
    button:hover { background: var(--accent-dark); } button.secondary { background: var(--strong); color: var(--accent-dark); border-color: var(--line); }
    button.secondary:hover { background: var(--accent-soft); } button:disabled { cursor: wait; opacity: .58; }
    input,select,textarea { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: var(--strong); color: var(--ink); padding: 9px 10px; }
    input:focus,select:focus,textarea:focus,button:focus-visible { outline: 3px solid #e8b58f; outline-offset: 1px; }
    textarea { resize: vertical; }
    .app { height:100vh; max-width: 1500px; margin: 0 auto; padding: 14px; display:flex; flex-direction:column; }
    .topbar { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:12px; flex:0 0 auto; }
    .title { margin:0; font-size:clamp(1.35rem,2vw,1.9rem); letter-spacing:.02em; } .subtitle { margin:5px 0 0; color:var(--muted); font-size:.9rem; }
    .top-actions { display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }
    .secondary-link { display:inline-flex; align-items:center; padding:9px 13px; border:1px solid var(--line); border-radius:9px; background:var(--strong); color:var(--accent-dark); text-decoration:none; font-size:.84rem; }
    .secondary-link:hover { background:var(--accent-soft); }
    .health { display:inline-flex; align-items:center; gap:7px; padding:8px 11px; border:1px solid var(--line); border-radius:99px; background:var(--paper); color:var(--muted); font-size:.84rem; }
    .health::before { content:""; width:8px; height:8px; border-radius:50%; background:var(--warn); } .health.ready { color:var(--good); } .health.ready::before { background:var(--good); }
    .layout { display:grid; flex:1; min-height:0; grid-template-columns:minmax(240px,285px) minmax(0,1fr) minmax(240px,310px); gap:14px; align-items:stretch; }
    .panel { min-width:0; min-height:0; border:1px solid var(--line); border-radius:14px; background:var(--paper); box-shadow:0 10px 28px #6c4a3214; }
    .panel-header { padding:16px 17px 10px; border-bottom:1px solid #eadbca; } .panel-header h2 { margin:0; font-size:1rem; }
    .panel-body { padding:14px 17px 17px; overflow:auto; } .field-grid { display:grid; gap:10px; }
    label { display:grid; gap:5px; color:var(--muted); font-size:.8rem; } .field-row { display:grid; grid-template-columns:1fr 1fr; gap:9px; } .field-wide { grid-column:1 / -1; }
    .quick-switch { display:grid; gap:5px; margin-top:9px; } .quick-switch-label { color:var(--muted); font-size:.76rem; } .npc-buttons { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:5px; } .npc-switch { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:5px 4px; border-color:var(--line); background:var(--strong); color:var(--accent-dark); font-size:.72rem; } .npc-switch:hover, .npc-switch.active { background:var(--accent); color:#fff; border-color:var(--accent-dark); }
    .hint { margin:5px 0 0; color:var(--muted); font-size:.76rem; line-height:1.45; } .scene-actions { display:flex; gap:8px; margin-top:13px; } .scene-actions button { flex:1; font-size:.8rem; }
    .transcript-panel { display:flex; flex-direction:column; min-height:0; } .transcript { flex:1; min-height:0; overflow:auto; padding:18px; background:#fbf4eb; border-bottom:1px solid #eadbca; }
    .empty { display:grid; place-items:center; min-height:250px; color:var(--muted); text-align:center; } .message { max-width:88%; margin:0 0 13px; padding:10px 12px; border:1px solid var(--line); border-radius:11px; line-height:1.55; white-space:pre-wrap; overflow-wrap:anywhere; }
    .message.npc { margin-right:auto; background:var(--npc); border-top-left-radius:4px; } .message.user { margin-left:auto; background:var(--player); border-color:#bfd0df; border-top-right-radius:4px; }
    .message-meta { margin-bottom:4px; color:var(--muted); font-size:.76rem; font-weight:700; } .composer { padding:14px 17px 16px; } .composer-row { display:flex; gap:9px; align-items:flex-end; }
    .composer textarea { min-height:62px; max-height:180px; } .composer-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:9px; } .composer-actions button { flex:1; min-width:110px; }
    .status { min-height:1.35em; margin:0 0 8px; color:var(--muted); font-size:.83rem; } .status.error { color:#9a4035; } .status.success { color:var(--good); }
    .stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; } .stat { padding:9px 10px; border:1px solid #eadbca; border-radius:9px; background:var(--strong); } .stat.usage-stat { grid-column:1 / -1; }
    .stat-label { color:var(--muted); font-size:.73rem; } .stat-value { margin-top:3px; font-size:.91rem; font-weight:700; overflow-wrap:anywhere; } details { margin-top:13px; border-top:1px solid #eadbca; padding-top:11px; }
    summary { cursor:pointer; color:var(--accent-dark); font-size:.84rem; font-weight:700; } .context-list { display:grid; gap:7px; margin:10px 0 0; color:var(--muted); font-size:.79rem; }
    .context-list strong { color:var(--ink); } pre { max-height:260px; margin:10px 0 0; overflow:auto; padding:10px; border-radius:8px; background:#f3ece4; color:#59483b; font-size:.72rem; white-space:pre-wrap; overflow-wrap:anywhere; }
    .warnings { margin:10px 0 0; color:var(--warn); font-size:.78rem; white-space:pre-wrap; } .raw-dialogue-count { margin:7px 0; color:var(--muted); font-size:.72rem; line-height:1.35; } .raw-dialogue-filter { margin:7px 0 9px; } .raw-section-title { margin:10px 0 5px; color:var(--accent-dark); font-size:.75rem; font-weight:700; } .raw-dialogue-list { display:grid; gap:6px; max-height:255px; overflow:auto; } .raw-entry { padding:7px 8px; border:1px solid #eadbca; border-radius:8px; background:var(--strong); } .raw-entry.pinned { border-color:#c9956e; background:#fff5e9; } .raw-entry-meta { color:var(--muted); font-size:.66rem; line-height:1.35; } .raw-entry-text { margin-top:4px; white-space:pre-wrap; overflow-wrap:anywhere; font-size:.73rem; line-height:1.45; } .raw-entry-source { margin-top:4px; color:var(--muted); font-size:.62rem; overflow-wrap:anywhere; } .raw-empty { padding:8px; color:var(--muted); font-size:.7rem; line-height:1.4; }
    .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
    @media (max-width:1050px) { .layout { grid-template-columns:minmax(220px,280px) minmax(0,1fr); } #diagnostics-panel { grid-column:1 / -1; } }
    @media (max-width:700px) { .app { padding:8px; } .topbar { align-items:center; margin-bottom:7px; } .subtitle { display:none; } .top-actions { gap:4px; } .top-actions button,.health { padding:5px 7px; font-size:.68rem; } .layout { display:grid; grid-template-columns:minmax(130px,.85fr) minmax(225px,1.45fr) minmax(130px,.85fr); gap:6px; } #diagnostics-panel { grid-column:auto; } #scene-panel,#diagnostics-panel { display:flex; flex-direction:column; } #scene-panel .panel-body,#diagnostics-panel .panel-body { flex:1; min-height:0; overflow:auto; } .panel-header { padding:9px 10px 7px; } .panel-body { padding:8px 9px 10px; } .field-grid { gap:6px; } label { font-size:.68rem; } input,select,textarea { padding:5px 6px; font-size:.72rem; } .quick-switch { margin-top:4px; } .npc-buttons { gap:4px; } .npc-switch { padding:5px 2px; font-size:.65rem; } .hint { font-size:.66rem; line-height:1.3; } .scene-actions { margin-top:7px; } .transcript { padding:8px; } .message { max-width:96%; margin-bottom:7px; padding:6px 8px; font-size:.72rem; line-height:1.35; } .message-meta { font-size:.66rem; } .composer { padding:8px 9px 10px; } .composer textarea { min-height:48px; } .composer-actions { gap:5px; margin-top:5px; } .composer-actions button { min-width:0; padding:6px 5px; font-size:.72rem; } .stat-grid { gap:5px; } .stat { padding:6px 7px; } .stat-label { font-size:.62rem; } .stat-value { font-size:.72rem; } details { margin-top:8px; padding-top:7px; } summary { font-size:.68rem; } .context-list { gap:4px; margin-top:6px; font-size:.66rem; } pre { margin-top:6px; padding:6px; font-size:.62rem; } .warnings { margin-top:6px; font-size:.64rem; } }
    @media (min-width:1051px) and (max-height:900px) { body { zoom:.76; } .app { height:calc(100vh / .76); } }
  </style>
</head>
<body>
  <main class="app">
    <header class="workspace-topbar topbar">
      <div class="workspace-brand brand"><div class="workspace-mark mark">✦</div><div><div class="workspace-eyebrow eyebrow">Stardew AI NPC · Dialogue Lab</div><strong>NPC 对话实验室</strong></div></div>
      <nav class="workspace-nav" aria-label="工作台导航"><a class="workspace-tab" href="/test">测试例浏览</a><a class="workspace-tab" href="/test/chat" aria-current="page">单次聊天</a><a class="workspace-tab" href="/raw">原始对白</a></nav>
      <div class="top-actions"><span id="health" class="health">Bridge 检查中……</span><a class="secondary-link" href="/raw">原始对白参照</a><button class="secondary" id="clear-session" type="button">清空会话</button><button class="secondary" id="export-session" type="button">导出 JSON</button></div>
    </header>
    <div class="layout">
      <section class="panel" id="scene-panel"><div class="panel-header"><h2>场景</h2></div><div class="panel-body"><div class="field-grid">
        <label data-npc-catalog="all">NPC（全部可聊天 NPC）<select id="npc-select"></select></label><div class="quick-switch"><span class="quick-switch-label">本次评测角色（只是快捷入口）</span><div id="npc-buttons" class="npc-buttons" role="group" aria-label="本次评测角色只是快捷入口"></div></div><label>聊天场景<select id="conversation-channel"><option value="face_to_face" selected>当面聊天</option><option value="remote">远程（手机/线上）</option></select></label><label>Provider 模式<select id="provider-mode"><option value="auto">自动（本地 → 云端 → 兜底）</option><option value="cloud" selected>云端（显式，当前配置）</option><option value="fake">Fake 演示（非真实 AI）</option></select></label>
        <label>显示名<input id="display-name" value="Rasmodia"></label><label>来源 Mod<input id="source-mods" value="Romanceable Rasmodius, Nom0ri.RomRas, Parrot.RomRas, Dacar.SeasRomRasmodia"></label>
        <label>关系阶段<select id="relationship-stage"><option value="stranger">初识</option><option value="acquaintance">熟悉</option><option value="friend" selected>朋友</option><option value="close">亲近</option><option value="dating">恋爱</option><option value="married">婚后</option><option value="parent">育儿</option></select></label>
        <div class="field-row"><label>季节<input id="season" value="春"></label><label>日期<input id="date" value="春 1 日"></label></div>
        <div class="field-row"><label>天气<input id="weather" value="晴天"></label><label>时间<input id="time" type="number" min="600" max="2600" step="10" value="800"></label></div>
        <label>地点<input id="location" value="法师塔"></label><label>好感度（原始点数）<input id="friendship" type="number" min="0" value="128"></label>
        <label class="field-wide">最近事实（每行一条）<textarea id="recent-facts" rows="3" placeholder="可选；只填写已确认事实"></textarea></label>
      </div><p class="hint">自动模式使用 Bridge 当前配置的 Provider；没有上游时会安全回退。Fake 只用于无网络的上下文演示。</p><div class="scene-actions"><button class="secondary" id="reset-scene" type="button">恢复默认场景</button></div></div></section>
      <section class="panel transcript-panel"><div class="panel-header"><h2>对话记录</h2></div><div class="transcript" id="transcript" aria-live="polite"><div class="empty" id="empty-transcript">还没有消息。输入一句话开始测试。</div></div>
        <div class="composer"><p class="status" id="status" aria-live="polite"></p><div class="composer-row"><textarea id="message-input" rows="2" placeholder="输入消息；Enter 发送，Shift+Enter 换行">你好，最近在研究什么？</textarea></div><div class="composer-actions"><button id="send" type="button">发送</button><button id="topic" class="secondary" type="button">主动找话题</button></div></div><div id="reply" class="sr-only" role="status"></div>
      </section>
      <aside class="panel" id="diagnostics-panel"><div class="panel-header"><h2>诊断</h2></div><div class="panel-body"><div class="stat-grid"><div class="stat"><div class="stat-label">Provider</div><div class="stat-value" id="provider-value">—</div></div><div class="stat"><div class="stat-label">延迟</div><div class="stat-value" id="latency-value">—</div></div><div class="stat"><div class="stat-label">Fallback</div><div class="stat-value" id="fallback-value">—</div></div><div class="stat"><div class="stat-label">消息数</div><div class="stat-value" id="message-count">0</div></div><div class="stat usage-stat"><div class="stat-label">本次 Token 用量</div><div class="stat-value" id="usage-value">—</div></div></div><div class="warnings" id="warnings" aria-live="polite"></div>
        <details open><summary>当前上下文摘要</summary><div class="context-list" id="context-summary"><span>发送消息后生成。</span></div></details><details><summary>本轮请求（脱敏）</summary><pre id="raw-request">尚未发送请求。</pre></details>
      </div></aside>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const messageInput = $("message-input");
    const SESSION_VERSION = 1;
    const EVALUATION_NPC_IDS = ["Wizard", "Sophia", "Shane", "Sebastian", "Alex"];
    const EVALUATION_PROFILES = [{npcId:"Wizard",label:"Rasmodia / Wizard",displayName:"Rasmodia",sourceMods:["Romanceable Rasmodius","Nom0ri.RomRas","Parrot.RomRas","Dacar.SeasRomRasmodia"]},{npcId:"Sophia",label:"Sophia",displayName:"Sophia",sourceMods:["SVE","FlashShifter.SVECode","FlashShifter.StardewValleyExpandedCP","FlashShifter.SVE-FTM"]},{npcId:"Shane",label:"Shane",displayName:"Shane",sourceMods:["female-bachelors","Invatorzen.idcsm","female.bachelors.beach","female.bachelors.winter"]},{npcId:"Sebastian",label:"Sebastian",displayName:"Sebastian",sourceMods:["female-bachelors","Invatorzen.idcsm","female.bachelors.beach","female.bachelors.winter"]},{npcId:"Alex",label:"Alex",displayName:"Alex",sourceMods:["vanilla"]}];
    const state = { messages: [], history: [], initialHistory: [], lastPayload: null, lastDiagnostics: null, npcs: [], activeEvaluationId:"Wizard", activeCaseId:"", pendingCase:null };
    function canonicalNpcId(npcId) { const value=typeof npcId==="string"?npcId.trim():""; return ["wizard","rasmodia"].includes(value.toLowerCase())?"Wizard":value; }
    function evaluationProfileForNpc(npcId) { const canonicalId=canonicalNpcId(npcId); return EVALUATION_PROFILES.find((profile)=>profile.npcId===canonicalId)||null; }
    function normalizeMessages(value) { return Array.isArray(value) ? value.filter((item)=>item&&["user","npc"].includes(item.role)&&typeof item.text==="string").map((item)=>({role:item.role,text:item.text,npcId:canonicalNpcId(typeof item.npcId==="string"&&item.npcId.trim()?item.npcId:"Wizard"),displayName:typeof item.displayName==="string"?item.displayName:"",createdAt:Number.isFinite(item.createdAt)?item.createdAt:null})).slice(-400) : []; }
    function normalizeHistory(value) { return Array.isArray(value) ? value.filter((item)=>item&&["user","assistant"].includes(item.role)&&typeof item.content==="string").map((item)=>({role:item.role,content:item.content})).slice(-50) : []; }
    function normalizeUsage(value) { if(!value||typeof value!=="object") return null; const usage={}; ["inputTokens","outputTokens","totalTokens"].forEach((key)=>{if(Number.isInteger(value[key])&&value[key]>=0)usage[key]=value[key];}); return Object.keys(usage).length?usage:null; }
    function formatUsage(usage) { if(!usage) return "—"; const parts=[]; if(Number.isInteger(usage.inputTokens))parts.push(`输入 ${usage.inputTokens}`); if(Number.isInteger(usage.outputTokens))parts.push(`输出 ${usage.outputTokens}`); if(Number.isInteger(usage.totalTokens))parts.push(`合计 ${usage.totalTokens}`); return parts.length?parts.join(" / "):"—"; }
    function normalizeDiagnostics(value) { if(!value||typeof value!=="object") return null; return {provider:typeof value.provider==="string"?value.provider:"",latencyMs:Number.isFinite(value.latencyMs)?value.latencyMs:null,fallback:Boolean(value.fallback),warnings:Array.isArray(value.warnings)?value.warnings.filter((item)=>typeof item==="string").slice(0,20):[],reply:typeof value.reply==="string"?value.reply:"",usage:normalizeUsage(value.usage)}; }
    function historyForNpc(npcId) { return normalizeHistory(state.messages.filter((item)=>canonicalNpcId(item.npcId)===canonicalNpcId(npcId)).map((item)=>({role:item.role==="user"?"user":"assistant",content:item.text}))); }
    async function saveSession() { const session={version:SESSION_VERSION,messages:state.messages,history:state.history,lastDiagnostics:normalizeDiagnostics(state.lastDiagnostics)}; try { const response=await fetch("/api/dialogue/session",{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify(session)}); if(!response.ok) throw new Error("本地会话保存失败"); return true; } catch (_) { return false; } }
    async function loadSession() { try { const response=await fetch("/api/dialogue/session"); if(!response.ok) throw new Error("本地会话加载失败"); const session=await response.json(); if(!session||session.version!==SESSION_VERSION){state.messages=[];state.history=[];state.initialHistory=[];state.lastDiagnostics=null;state.lastPayload=null;return;} state.messages=normalizeMessages(session.messages);state.history=normalizeHistory(session.history);state.initialHistory=[];state.lastDiagnostics=normalizeDiagnostics(session.lastDiagnostics);state.lastPayload=null; } catch (_) { state.messages=[];state.history=[];state.initialHistory=[];state.lastDiagnostics=null;state.lastPayload=null; } }
    const stageState = { stranger:{friendshipHearts:0,relationship:"未婚"}, acquaintance:{friendshipHearts:3,relationship:"未婚"}, friend:{friendshipHearts:6,relationship:"朋友"}, close:{friendshipHearts:8,relationship:"朋友"}, dating:{friendshipHearts:8,relationship:"dating"}, married:{friendshipHearts:10,relationship:"married",marriageStatus:"married"}, parent:{friendshipHearts:10,relationship:"married",marriageStatus:"married",childrenCount:1} };
    function selectedNpc() { const option = $("npc-select").selectedOptions[0]; return { npcId:canonicalNpcId(option?.value || "Wizard"), displayName: $("display-name").value.trim() || option?.textContent || "NPC" }; }
    function npcIdsForButtons(){const known=new Set(state.npcs.map((npc)=>npc.npcId));return EVALUATION_NPC_IDS.filter((npcId)=>known.has(npcId));}
    function renderNpcButtons(){const container=$("npc-buttons");if(!container)return;container.replaceChildren();const selected=canonicalNpcId(selectedNpc().npcId);for(const npcId of npcIdsForButtons()){const profile=evaluationProfileForNpc(npcId);if(!profile)continue;const button=document.createElement("button");button.type="button";button.className=`npc-switch ${npcId===selected?"active":""}`;button.dataset.npcId=npcId;button.textContent=profile.label;button.setAttribute("aria-pressed",String(npcId===selected));button.title=`切换到 ${profile.label}`;button.addEventListener("click",()=>switchNpc(npcId));container.append(button);}}
    function applyEvaluationProfile(npcId){const profile=evaluationProfileForNpc(npcId);if(!profile)return;const select=$("npc-select");if(!Array.from(select.options).some((option)=>option.value===profile.npcId))return;select.value=profile.npcId;state.activeEvaluationId=profile.npcId;$("display-name").value=profile.displayName;$("source-mods").value=profile.sourceMods.join(", ");}
    async function switchNpc(npcId){await loadSession();const profile=evaluationProfileForNpc(npcId);if(!profile)return;applyEvaluationProfile(profile.npcId);state.activeCaseId="";state.pendingCase=null;state.initialHistory=[];state.history=historyForNpc(profile.npcId);state.lastPayload=null;state.lastDiagnostics=null;renderTranscript();renderDiagnostics();renderNpcButtons();window.dispatchEvent(new CustomEvent("dialogue-lab:npc-selected",{detail:{npcId:profile.npcId,displayName:profile.displayName,source:"chat"}}));}
    function applyQualityCase(item){if(!item)return;state.pendingCase=item;state.activeCaseId=item.caseId||"";applyEvaluationProfile(item.npcId||"Wizard");const gameState=item.gameState||{};if(item.relationshipStage)$('relationship-stage').value=item.relationshipStage;if(gameState.season!==undefined)$('season').value=String(gameState.season);if(gameState.date!==undefined)$('date').value=String(gameState.date);if(gameState.weather!==undefined)$('weather').value=String(gameState.weather);if(gameState.time!==undefined)$('time').value=String(gameState.time);if(gameState.location!==undefined)$('location').value=String(gameState.location);if(gameState.friendshipHearts!==undefined)$('friendship').value=String(Number(gameState.friendshipHearts)*2);if(item.channel)$('conversation-channel').value=item.channel;if(item.storyProgress!==undefined)$('recent-facts').value=item.storyProgress||"";if(item.playerInput!==undefined)$('message-input').value=item.playerInput||"";state.initialHistory=normalizeHistory(item.history);state.history=[];state.lastPayload=null;state.lastDiagnostics=null;renderTranscript();renderDiagnostics();setStatus(`已带入 ${item.caseId||"当前测试例"}，可以发送验证。`,"success");}
    function sceneState() { const stage = stageState[$("relationship-stage").value] || stageState.friend; const gameState = {...stage, season:$("season").value.trim(), date:$("date").value.trim(), weather:$("weather").value.trim(), location:$("location").value.trim(), friendship:Number($("friendship").value)||0}; const time=Number($("time").value); if(Number.isFinite(time)&&time>0) gameState.time=time; return gameState; }
     function buildPayload(message,intent="chat") { const npc=selectedNpc(); const profile=evaluationProfileForNpc(npc.npcId)||{sourceMods:$('source-mods').value.split(',').map((item)=>item.trim()).filter(Boolean)}; const payload={npcId:npc.npcId,displayName:npc.displayName,sourceMods:profile.sourceMods,recentFacts:$('recent-facts').value.split("\\n").map((item)=>item.trim()).filter(Boolean),message,intent,history:[...state.initialHistory,...state.history].slice(-50),gameState:sceneState(),channel:$("conversation-channel").value}; if($("provider-mode").value!=="auto") payload.provider=$("provider-mode").value; return payload; }
    function renderTranscript() { const transcript=$("transcript"); transcript.replaceChildren(); const npc=selectedNpc(); const messages=state.messages.filter((message)=>message.npcId===npc.npcId); if(!messages.length){const empty=document.createElement("div");empty.className="empty";empty.id="empty-transcript";empty.textContent=`当前角色没有已保存记录。切换到${npc.displayName}后，可在此发送消息。`;transcript.append(empty);$("message-count").textContent="0";return;} for(const message of messages){const bubble=document.createElement("article");bubble.className=`message ${message.role==="user"?"user":"npc"}`;const meta=document.createElement("div");meta.className="message-meta";meta.textContent=message.role==="user"?"你":message.displayName||message.npcId||npc.displayName;const body=document.createElement("div");body.textContent=message.text;bubble.append(meta,body);transcript.append(bubble);} transcript.scrollTop=transcript.scrollHeight;$("message-count").textContent=String(messages.length); }
    function setStatus(text,kind=""){const status=$("status");status.textContent=text;status.className=`status ${kind}`;}
    function renderDiagnostics(){const data=state.lastDiagnostics;$("provider-value").textContent=data?.provider||"—";$("latency-value").textContent=Number.isFinite(data?.latencyMs)?`${data.latencyMs} ms`:"—";$("fallback-value").textContent=data?data.fallback?"是":"否":"—";$("usage-value").textContent=formatUsage(data?.usage);$("warnings").textContent=data?.warnings?.length?`提示：${data.warnings.join("；")}`:"";$("raw-request").textContent=state.lastPayload?JSON.stringify(state.lastPayload,null,2):data?"会话已恢复；原始请求未保存。":"尚未发送请求。";$("reply").textContent=data?.reply||"";}
    function updateDiagnostics(data,payload){state.lastDiagnostics=normalizeDiagnostics(data);state.lastPayload=payload;renderDiagnostics();}
    function renderContext(context){const summary=$("context-summary");summary.replaceChildren();const identity=context.personaSummary||{};const evidenceSources=[...new Set((context.speechEvidence||[]).map((item)=>item?.sourceMod).filter(Boolean))];const rows=[["角色",identity.displayName||identity.npcId||"—"],["关系阶段",identity.stageProfile?.stage||"由当前场景推断"],["来源 Mod",(context.modSources||[]).join("、")||"—"],["原文证据来源",evidenceSources.join("、")||"未取到来源原文"],["事实",`${(context.recentFacts||[]).length} 条`],["风格证据",`${(context.speechEvidence||context.styleSamples||[]).length} 条`],["故事事件",`${(context.storyEvents||[]).length} 条`]];for(const [label,value] of rows){const row=document.createElement("div");const strong=document.createElement("strong");strong.textContent=label;row.append(strong,document.createTextNode(`：${value}`));summary.append(row);}}
    function errorText(data,fallback){if(Array.isArray(data?.detail))return data.detail.map((item)=>item.msg||"请求参数错误").join("；");return data?.detail||data?.message||fallback;}
    async function refreshContext(payload){try{const response=await fetch("/api/context/preview",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});if(response.ok)renderContext(await response.json());}catch(_){/* 摘要失败不覆盖已收到的回复 */}}
    async function sendDialogue(intent="chat"){const text=messageInput.value.trim();if(!text&&intent==="chat"){setStatus("请先输入消息。","error");return;}const outgoing=text||"请结合当前场景主动找一个合适的话题。";const npc=selectedNpc();const payload=buildPayload(outgoing,intent);const initialHistory=state.initialHistory.slice();$("send").disabled=true;$("topic").disabled=true;setStatus("请求中……");try{const response=await fetch("/api/dialogue/test",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw new Error(errorText(data,"对话请求失败"));state.messages.push({role:"user",text:intent==="topic"?"（请主动找话题）":outgoing,npcId:npc.npcId,displayName:npc.displayName,createdAt:Date.now()});state.messages.push({role:"npc",text:data.reply,npcId:npc.npcId,displayName:npc.displayName,createdAt:Date.now()});state.initialHistory=[];state.history=normalizeHistory([...initialHistory,...historyForNpc(npc.npcId)]);if(intent==="chat")messageInput.value="";updateDiagnostics(data,payload);renderTranscript();const persisted=await saveSession();setStatus(persisted?"已收到回复。":"已收到回复，但本地记录保存失败。",persisted?"success":"error");await refreshContext(payload);}catch(error){setStatus(`请求失败，保留输入：${error.message}`,"error");}finally{$("send").disabled=false;$("topic").disabled=false;}}
    function resetScene(){$("relationship-stage").value="friend";$("season").value="春";$("date").value="春 1 日";$("weather").value="晴天";$("time").value="800";$("location").value="法师塔";$("friendship").value="128";$("recent-facts").value="";state.activeCaseId="";state.pendingCase=null;state.initialHistory=[];applyEvaluationProfile(state.activeEvaluationId||"Wizard");window.dispatchEvent(new CustomEvent("dialogue-lab:npc-selected",{detail:{...selectedNpc(),source:"chat"}}));}
    async function clearSession(){state.messages=[];state.history=[];state.lastPayload=null;state.lastDiagnostics=null;renderTranscript();renderDiagnostics();$("context-summary").innerHTML="<span>发送消息后生成。</span>";try{const response=await fetch("/api/dialogue/session",{method:"DELETE"});if(!response.ok)throw new Error("本地会话清理失败");setStatus("会话已清空。","success");}catch(error){setStatus(`页面已清空，但本地文件清理失败：${error.message}`,"error");}}
    function exportSession(){const exportData={exportedAt:new Date().toISOString(),npc:selectedNpc(),gameState:sceneState(),messages:state.messages,history:state.history,lastDiagnostics:state.lastDiagnostics};const link=document.createElement("a");link.href=URL.createObjectURL(new Blob([JSON.stringify(exportData,null,2)],{type:"application/json"}));link.download=`stardew-dialogue-${Date.now()}.json`;link.click();URL.revokeObjectURL(link.href);}
    async function loadNpcs(){const response=await fetch("/api/npcs");if(!response.ok)throw new Error("NPC 资料加载失败");state.npcs=(await response.json()).npcs||[];const select=$("npc-select");select.replaceChildren();for(const npc of state.npcs){const option=document.createElement("option");option.value=npc.npcId;option.textContent=`${npc.displayName} (${npc.npcId})`;option.title=Array.isArray(npc.sourceMods)&&npc.sourceMods.length?`来源：${npc.sourceMods.join("、")}`:"暂无来源标记";option.dataset.hasDialogueEvidence=String(Boolean(npc.hasDialogueEvidence));select.append(option);}applyEvaluationProfile("Wizard");select.addEventListener("change",async()=>{await loadSession();const canonicalId=canonicalNpcId(select.value);const profile=evaluationProfileForNpc(canonicalId);if(profile){state.activeEvaluationId=profile.npcId;$("display-name").value=profile.displayName;$("source-mods").value=profile.sourceMods.join(", ");}else{const selected=state.npcs.find((npc)=>canonicalNpcId(npc.npcId)===canonicalId);$("display-name").value=selected?.displayName||canonicalId;$("source-mods").value=Array.isArray(selected?.sourceMods)?selected.sourceMods.join(", "):"";}state.activeCaseId="";state.initialHistory=[];state.history=historyForNpc(canonicalId);state.lastPayload=null;state.lastDiagnostics=null;renderTranscript();renderDiagnostics();renderNpcButtons();window.dispatchEvent(new CustomEvent("dialogue-lab:npc-selected",{detail:{...selectedNpc(),source:"chat"}}));});state.history=historyForNpc(select.value);renderTranscript();renderDiagnostics();renderNpcButtons();if(state.pendingCase)applyQualityCase(state.pendingCase);}
    window.addEventListener("dialogue-lab:apply-case",(event)=>applyQualityCase(event.detail));
    window.addEventListener("dialogue-lab:npc-selected",async(event)=>{if(event.detail?.source==="chat")return;const profile=evaluationProfileForNpc(event.detail?.npcId);if(!profile)return;await loadSession();applyEvaluationProfile(profile.npcId);state.activeCaseId="";state.pendingCase=null;state.initialHistory=[];state.history=historyForNpc(profile.npcId);state.lastPayload=null;state.lastDiagnostics=null;renderTranscript();renderDiagnostics();renderNpcButtons();});
    async function loadHealth(){try{const response=await fetch("/health");const data=await response.json();if(!response.ok)throw new Error();$("health").textContent=`Bridge 在线 · ${data.provider}`;$("health").classList.add("ready");}catch(_){$("health").textContent="Bridge 不可用";}}
    $("send").addEventListener("click",()=>sendDialogue());$("topic").addEventListener("click",()=>sendDialogue("topic"));$("clear-session").addEventListener("click",clearSession);$("export-session").addEventListener("click",exportSession);$("reset-scene").addEventListener("click",resetScene);messageInput.addEventListener("keydown",(event)=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();sendDialogue();}});async function initializeLab(){await loadSession();renderTranscript();renderDiagnostics();Promise.all([loadNpcs(),loadHealth()]).catch((error)=>setStatus(error.message,"error"));}initializeLab();
  </script>
</body>
</html>
"""


DIALOGUE_CASE_BROWSER_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stardew AI NPC · 测试例浏览器</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
      --ink:#2f382f; --muted:#738076; --line:#d9e0d8; --paper:#fffef9; --soft:#f1f5ef;
      --green:#3f7054; --green-soft:#e8f2e9; --gold:#b37c2d; --gold-soft:#fff1d7;
      --rose:#a45550; --rose-soft:#f8e8e5; --shadow:0 12px 30px #3d5d4614; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; overflow:hidden; background:#e8eee8; color:var(--ink); }
    button,select { font:inherit; }
    button { cursor:pointer; }
    .app { height:100vh; max-width:1560px; margin:0 auto; padding:14px 18px; display:flex; flex-direction:column; }
    .topbar { display:flex; align-items:center; gap:18px; flex:0 0 auto; margin-bottom:12px; padding:11px 14px; border-radius:13px;
      color:#f9faf4; background:linear-gradient(110deg,#294b3b,#3c6b52); box-shadow:0 4px 15px #244a351f; }
    .brand { display:flex; align-items:center; gap:10px; min-width:260px; }
    .mark { width:31px; height:31px; display:grid; place-items:center; border:1px solid #ffffff3d; border-radius:9px; color:#f1d085; background:#ffffff12; font-size:17px; }
    .eyebrow { color:#d6e4d6; font-size:9px; letter-spacing:.13em; text-transform:uppercase; }
    .brand strong { display:block; margin-top:2px; font-size:14px; }
    .tabs { display:flex; align-self:stretch; align-items:center; gap:4px; }
    .tab { padding:8px 12px; border:0; border-radius:7px; color:#d5e3d5; background:transparent; text-decoration:none; font-size:12px; }
    .tab:hover,.tab.active { color:#fff; background:#ffffff19; }
    .top-meta { display:flex; align-items:center; gap:10px; margin-left:auto; color:#d7e5d8; font-size:10px; }
    .prototype { color:#f0cd82; }
    .health { display:inline-flex; align-items:center; gap:6px; padding:6px 9px; border:1px solid #ffffff27; border-radius:20px; background:#17382735; }
    .health:before { content:""; width:7px; height:7px; border-radius:50%; background:#90d19b; }
    .heading { display:flex; align-items:end; justify-content:space-between; flex:0 0 auto; margin:0 2px 11px; }
    .heading h1 { margin:0; font-size:22px; letter-spacing:-.03em; }
    .heading p { margin:4px 0 0; color:var(--muted); font-size:12px; }
    .heading-actions { display:flex; gap:7px; }
    .btn { padding:7px 10px; border:1px solid var(--line); border-radius:8px; color:var(--ink); background:#ffffffc9; text-decoration:none; font-size:11px; }
    .btn:hover { border-color:#9cbaa4; background:#fff; }
    .btn.gold { color:#795821; border-color:#d6b273; background:var(--gold-soft); }
    .browser-layout { display:grid; grid-template-columns:220px minmax(0,1fr) 275px; gap:12px; flex:1; min-height:0; }
    .panel { min-width:0; min-height:0; overflow:hidden; border:1px solid #d2dbd1; border-radius:13px; background:#fffffff0; box-shadow:var(--shadow); }
    .panel-header { display:flex; align-items:center; justify-content:space-between; height:45px; padding:0 13px; border-bottom:1px solid var(--line); background:#fafcf8; }
    .panel-header h2 { margin:0; font-size:13px; }
    .kicker { color:var(--muted); font-size:9px; letter-spacing:.12em; text-transform:uppercase; }
    .panel-body { min-height:0; overflow:auto; padding:12px; }
    .nav-panel,.detail-panel,.coverage-panel { display:flex; flex-direction:column; }
    .nav-panel .panel-body,.detail-panel .panel-body,.coverage-panel .panel-body { flex:1; }
    .batch-card { padding:10px; border:1px solid #d7e5d8; border-radius:9px; background:linear-gradient(135deg,#edf6ee,#fbfcf7); }
    .batch-card small { color:var(--green); font-size:9px; letter-spacing:.08em; text-transform:uppercase; }
    .batch-card strong { display:block; margin-top:3px; color:#315d45; font-size:14px; }
    .batch-card span { color:var(--muted); font-size:10px; }
    .nav-section { margin-top:14px; }
    .section-head { display:flex; justify-content:space-between; margin-bottom:6px; }
    .section-head strong { font-size:10px; } .section-head span { color:var(--muted); font-size:9px; }
    .filter-list,.case-list { display:grid; gap:4px; }
    .filter-btn,.case-row { width:100%; border-radius:7px; text-align:left; }
    .filter-btn { padding:6px 8px; border:1px solid transparent; color:#647269; background:transparent; font-size:10px; }
    .filter-btn:hover { background:var(--soft); } .filter-btn.active { border-color:#bdd2bf; color:var(--green); background:var(--green-soft); font-weight:600; }
    .filter-btn span { float:right; color:var(--muted); font-size:9px; }
    .case-row { padding:7px 8px; border:1px solid transparent; color:var(--ink); background:#fff; }
    .case-row:hover { border-color:#c9dbce; } .case-row.active { border-color:#98b99f; background:#f0f7ef; }
    .case-top { display:flex; justify-content:space-between; gap:4px; } .case-id { color:var(--muted); font-size:9px; font-weight:700; }
    .case-kind { color:#a2712a; font-size:8px; } .case-title { margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:10px; font-weight:600; }
    .case-meta { display:flex; gap:4px; margin-top:3px; color:var(--muted); font-size:8px; }
    .nav-note { margin-top:13px; padding:8px; border-radius:7px; color:#6d796f; background:var(--soft); font-size:9px; line-height:1.5; }
    .detail-panel .panel-body { padding:14px 15px; }
    .detail-heading { display:flex; justify-content:space-between; gap:12px; }
    .detail-heading h2 { margin:0; font-size:18px; letter-spacing:-.02em; } .detail-heading p { margin:4px 0 0; color:var(--muted); font-size:10px; }
    .case-status { padding:5px 7px; border-radius:5px; color:#896225; background:var(--gold-soft); font-size:9px; white-space:nowrap; }
    .context-strip { display:flex; flex-wrap:wrap; gap:5px; margin:12px 0; }
    .context-chip { padding:5px 7px; border:1px solid #dfe7de; border-radius:6px; color:#5f7064; background:#f5f8f3; font-size:9px; }
    .context-chip b { margin-right:4px; color:#8a968c; font-weight:500; }
    .scene-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; }
    .scene-fact { padding:7px 8px; border:1px solid #e1e8df; border-radius:7px; background:#f7faf6; }
    .scene-label { display:block; color:#8a968c; font-size:8px; }
    .scene-value { display:block; margin-top:2px; color:#405948; font-size:10px; font-weight:600; overflow-wrap:anywhere; }
    .story-progress { margin-top:7px; padding:8px 9px; border-left:3px solid #d0ad63; border-radius:0 7px 7px 0; color:#6f6040; background:#fff9e9; font-size:10px; line-height:1.5; }
    .story-progress b { display:block; margin-bottom:2px; color:#8a6a2e; font-size:9px; }
    .prompt-card { display:grid; grid-template-columns:minmax(0,1fr) 205px; gap:12px; padding:11px; border:1px solid #e3dfd2; border-radius:9px; background:linear-gradient(135deg,#fffdf5,#fbfaf3); }
    .prompt-label { color:#a0712a; font-size:9px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
    .prompt-text { margin-top:3px; font-size:14px; font-weight:600; } .goal { padding-left:11px; border-left:1px solid #e6decb; }
    .goal strong { font-size:10px; } .goal p { margin:4px 0 0; color:#6c776e; font-size:9px; line-height:1.5; }
    .detail-block { margin-top:13px; } .detail-block h3 { margin:0 0 6px; font-size:11px; }
    .term-row { display:flex; flex-wrap:wrap; gap:5px; } .term { padding:4px 6px; border-radius:5px; color:#4c7657; background:var(--green-soft); font-size:9px; }
    .term.forbidden { color:var(--rose); background:var(--rose-soft); } .term.empty { color:var(--muted); background:var(--soft); }
    .history { padding:8px 9px; border-left:3px solid #b4c9b7; border-radius:0 7px 7px 0; color:#68756b; background:#f3f6f1; font-size:10px; line-height:1.55; }
    .history div + div { margin-top:4px; } .history b { color:var(--green); font-size:9px; }
    .provenance { margin-top:12px; padding:8px 9px; border:1px dashed #d3ddd2; border-radius:7px; color:var(--muted); font-size:9px; line-height:1.5; }
    .result-card { margin-top:13px; padding:11px; border:1px solid #c9dccb; border-radius:9px; background:linear-gradient(135deg,#f1f8f0,#fbfcf7); }
    .result-card.review { border-color:#ead4aa; background:#fffaf0; }
    .result-card.error { border-color:#e2bdb7; background:#fff5f3; }
    .result-card-header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .result-card-header strong { color:#315d43; font-size:12px; }
    .result-card.review .result-card-header strong { color:#896225; }
    .result-card.error .result-card-header strong { color:#994d45; }
    .result-status { padding:4px 6px; border-radius:5px; color:#326143; background:#e4f1e4; font-size:9px; white-space:nowrap; }
    .result-card.review .result-status { color:#896225; background:#fff0d0; }
    .result-card.error .result-status { color:#994d45; background:#f8e4e0; }
    .result-label { margin-top:9px; color:#6b7b6d; font-size:9px; font-weight:700; letter-spacing:.05em; }
    .result-reply { margin-top:4px; padding:8px 9px; border-left:3px solid #80a98b; border-radius:0 7px 7px 0; color:#344a38; background:#fff; font-size:13px; line-height:1.6; white-space:pre-wrap; overflow-wrap:anywhere; }
    .result-card.review .result-reply { border-left-color:#d0ad63; color:#625133; }
    .result-card.error .result-reply { border-left-color:#c47a70; color:#70413b; }
    .result-meta { margin-top:7px; color:#6d796f; font-size:10px; line-height:1.45; }
    .result-tags { margin-top:5px; color:#896225; font-size:10px; line-height:1.45; }
    .result-warning { margin-top:5px; color:#896225; font-size:10px; line-height:1.45; }
    .transcript-card { margin-top:13px; padding:11px; border:1px solid #c9dccb; border-radius:9px; background:linear-gradient(135deg,#f1f8f0,#fbfcf7); }
    .transcript-card.review { border-color:#ead4aa; background:#fffaf0; }
    .transcript-card.error { border-color:#e2bdb7; background:#fff5f3; }
    .transcript-card-header { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
    .transcript-card-header strong { color:#315d43; font-size:12px; }
    .transcript-summary { margin-top:3px; color:#6d796f; font-size:10px; line-height:1.45; }
    .transcript-history { margin-top:9px; padding:8px 9px; border-left:3px solid #b4c9b7; border-radius:0 7px 7px 0; color:#68756b; background:#f3f6f1; font-size:10px; line-height:1.55; }
    .transcript-history-title { margin-bottom:4px; color:var(--green); font-size:9px; font-weight:700; }
    .transcript-history-line + .transcript-history-line { margin-top:4px; }
    .transcript-history-line b { color:var(--green); font-size:9px; }
    .transcript-turn { margin-top:9px; padding:9px; border:1px solid #e0e8df; border-radius:8px; background:#fff; }
    .transcript-turn.review { border-color:#ead4aa; background:#fffdf7; }
    .transcript-turn.error { border-color:#e2bdb7; background:#fff8f6; }
    .transcript-turn-head { display:flex; align-items:center; justify-content:space-between; gap:8px; color:#4b6e54; font-size:10px; font-weight:700; }
    .transcript-turn-state { padding:3px 5px; border-radius:4px; color:#6d796f; background:#eef3ed; font-size:9px; font-weight:500; white-space:nowrap; }
    .transcript-turn-state.ready { color:#896225; background:#fff0d0; }
    .transcript-turn-label { margin-top:7px; color:#8a968c; font-size:9px; font-weight:700; }
    .transcript-turn-player,.transcript-turn-reply { margin-top:3px; padding:7px 8px; border-radius:6px; font-size:11px; line-height:1.55; white-space:pre-wrap; overflow-wrap:anywhere; }
    .transcript-turn-player { color:#5f5a45; background:#fff9e9; }
    .transcript-turn-reply { color:#344a38; background:#f5faf4; }
    .transcript-turn-reply.pending { color:#8a968c; background:#f5f7f3; }
    .transcript-turn-meta,.transcript-turn-score { margin-top:5px; color:#6d796f; font-size:9px; line-height:1.45; }
    .transcript-turn-score { color:#896225; }
    .transcript-empty { margin-top:9px; padding:9px; color:#8a968c; background:#f5f7f3; font-size:10px; line-height:1.5; }
    .batch-run-status { display:block; margin-top:3px; color:#52745a; font-size:10px; }
    .coverage-intro { padding:9px; border-radius:8px; color:#67746b; background:var(--soft); font-size:9px; line-height:1.5; }
    .coverage-intro b { color:var(--green); } .coverage-section { margin-top:14px; }
    .coverage-section h3 { margin:0 0 7px; font-size:11px; } .metric-list { display:grid; gap:7px; }
    .metric { display:flex; justify-content:space-between; padding-bottom:6px; border-bottom:1px dashed #e0e5df; font-size:10px; }
    .metric span { color:var(--muted); } .metric strong { color:var(--green); }
    .bar-row { display:grid; grid-template-columns:72px 1fr 20px; align-items:center; gap:5px; margin:6px 0; color:#68756b; font-size:9px; }
    .bar { height:6px; overflow:hidden; border-radius:5px; background:#e7ece6; } .bar i { display:block; height:100%; border-radius:5px; background:#80a98b; }
    .gap-box { padding:9px; border:1px solid #eadbbf; border-radius:8px; color:#81672f; background:var(--gold-soft); font-size:9px; line-height:1.55; }
    .gap-box strong { display:block; margin-bottom:3px; color:#76571d; font-size:10px; }
    .coverage-actions { display:grid; gap:6px; margin-top:14px; } .coverage-actions a { text-align:left; }
    .empty-state { display:grid; place-items:center; min-height:220px; color:var(--muted); text-align:center; font-size:11px; }
    .toast { position:fixed; right:23px; bottom:20px; padding:9px 12px; border:1px solid #bdd2be; border-radius:8px; color:#326143; background:#f2faf1; box-shadow:var(--shadow); opacity:0; transform:translateY(8px); transition:.2s; pointer-events:none; font-size:10px; }
    .toast.show { opacity:1; transform:translateY(0); }
    @media (max-width:1050px) { body { overflow:auto; } .app { height:auto; min-height:100vh; } .topbar { flex-wrap:wrap; } .top-meta { margin-left:0; } .browser-layout { grid-template-columns:210px minmax(0,1fr); min-height:800px; } .coverage-panel { grid-column:1 / -1; min-height:260px; } }
    @media (max-width:700px) { .app { padding:8px; } .browser-layout { grid-template-columns:1fr; } .nav-panel,.coverage-panel { max-height:360px; } .coverage-panel { grid-column:auto; } .prompt-card { grid-template-columns:1fr; } .goal { padding:0; border:0; border-top:1px solid #e6decb; padding-top:8px; } }
  </style>
</head>
<body>
  <main class="app" id="test-case-browser">
    <header class="workspace-topbar topbar"><div class="workspace-brand brand"><div class="workspace-mark mark">✦</div><div><div class="workspace-eyebrow eyebrow">Stardew AI NPC · Dialogue Lab</div><strong>角色对话评测工作台</strong></div></div><nav class="workspace-nav" aria-label="工作台导航"><a class="workspace-tab" href="/test" aria-current="page">测试例浏览</a><a class="workspace-tab" href="/test/chat">单次聊天</a><a class="workspace-tab" href="/raw">原始对白</a></nav><div class="top-meta"><span class="prototype">查看模式 · 不发送请求</span><span id="health" class="health">Bridge 检查中……</span></div></header>
    <div class="heading"><div><h1>测试例浏览器</h1><p>先看不同条件下我们到底测了什么，再判断模型回复是否贴合。</p></div><div class="heading-actions"><a class="btn" href="/test/chat">打开单次聊天</a><button class="btn gold" id="export-case" type="button">导出当前例</button></div></div>
    <div class="browser-layout">
      <aside class="panel nav-panel"><div class="panel-header"><h2>测试例导航</h2><span class="kicker">Cases</span></div><div class="panel-body"><div class="batch-card"><small>当前质量批次</small><strong id="batch-title">固定角色场景</strong><span id="batch-summary">加载案例中……</span><span id="batch-run-status" class="batch-run-status"></span></div><div class="nav-section"><div class="section-head"><strong>按类型筛选</strong><span>查看定义与结果</span></div><div class="filter-list"><button class="filter-btn active" data-filter="all">全部测试例 <span id="filter-all-count">—</span></button><button class="filter-btn" data-filter="daily">日常状态 <span id="filter-daily-count">—</span></button><button class="filter-btn" data-filter="channel">远程 / 当面 <span id="filter-channel-count">—</span></button><button class="filter-btn" data-filter="continuity">上下文续聊 <span id="filter-continuity-count">—</span></button></div></div><div class="nav-section"><div class="section-head"><strong>场景列表</strong><span id="visible-case-count">—</span></div><div class="case-list" id="case-list"><div class="empty-state">正在加载测试例……</div></div></div><div class="nav-note">点击一个例子，中央会展开场景条件、预置历史和本轮真实模型回复；自动评分只作提示，最终仍看人物是否贴切。</div></div></aside>
      <section class="panel detail-panel"><div class="panel-header"><h2>当前测试例</h2><span class="kicker">Case detail</span></div><div class="panel-body" id="case-detail"><div class="empty-state">正在加载测试例……</div></div></section>
      <aside class="panel coverage-panel" id="coverage-panel"><div class="panel-header"><h2>覆盖情况</h2><span class="kicker">Coverage</span></div><div class="panel-body"><div class="coverage-intro">这里同时展示固定场景覆盖和最新生成结果。当前查看 <b id="coverage-current">—</b>；自动评分不是人工角色判断。</div><div class="coverage-section"><h3>批次概览</h3><div class="metric-list"><div class="metric"><span>测试例总数</span><strong id="coverage-total">—</strong></div><div class="metric"><span>角色数</span><strong id="coverage-roles">—</strong></div><div class="metric"><span>预置上下文</span><strong id="coverage-history">—</strong></div><div class="metric"><span>聊天渠道</span><strong id="coverage-channels">—</strong></div><div class="metric"><span>场景字段</span><strong id="coverage-scenes">—</strong></div><div class="metric"><span>生成轮数</span><strong id="coverage-turns">—</strong></div><div class="metric"><span>Token 用量</span><strong id="coverage-tokens">—</strong></div><div class="metric"><span>估算费用</span><strong id="coverage-cost">—</strong></div></div></div><div class="coverage-section"><h3>关系阶段分布</h3><div id="stage-bars"></div></div><div class="coverage-section"><h3>渠道分布</h3><div id="channel-bars"></div></div><div class="coverage-section"><div class="gap-box"><strong>人工复核提示</strong><span>每个案例仍带季节、日期、天气、地点 / 时间 / 天气、好感度和剧情进度；结果中的通过/失败只反映证据词、禁用词和格式检查，请重点看回复是否像这个角色、是否自然、是否机械回扣。</span></div></div><div class="coverage-actions"><a class="btn" href="/test/chat">去单次聊天验证当前例</a><button class="btn" id="show-all" type="button">回到全部测试例</button></div></div></aside>
    </div>
  </main>
  <div class="toast" id="toast" role="status"></div>
  <script>
    const $ = (id) => document.getElementById(id);
    const state = { cases: [], selectedCaseId: "", filter: "all", results: {}, run: null };
    const stageLabels = { stranger:"初识", acquaintance:"熟悉", friend:"朋友", close:"亲近", dating:"恋爱", married:"婚后", parent:"育儿" };
    const channelLabels = { remote:"远程（手机/线上）", face_to_face:"当面聊天" };
    const roleNames = { Wizard:"Rasmodia / Wizard", Sophia:"Sophia", Shane:"Shane", Sebastian:"Sebastian", Alex:"Alex" };
    function categoryOf(item) { if (Array.isArray(item.history) && item.history.length) return "continuity"; if (item.channel === "remote") return "channel"; return "daily"; }
    function categoryLabel(item) { return categoryOf(item) === "continuity" ? "上下文续聊" : categoryOf(item) === "channel" ? "渠道场景" : "日常状态"; }
    function visibleCases() { return state.cases.filter((item) => state.filter === "all" || categoryOf(item) === state.filter); }
    function selectCase(item, openChat = false) { if (!item) return; state.selectedCaseId = item.caseId; renderCaseList(); renderCaseDetail(); window.dispatchEvent(new CustomEvent("dialogue-lab:case-selected", { detail: item })); if (openChat) window.DialogueLab?.showView("chat"); }
    function showToast(message) { const el = $("toast"); el.textContent = message; el.classList.add("show"); clearTimeout(window.__caseToast); window.__caseToast = setTimeout(() => el.classList.remove("show"), 1700); }
    function renderFilterCounts() { const counts = {all:state.cases.length,daily:0,channel:0,continuity:0}; state.cases.forEach((item) => counts[categoryOf(item)] += 1); Object.entries(counts).forEach(([key,value]) => { const element = $(`filter-${key}-count`); if (element) element.textContent = value; }); }
    function resultStatus(item) { const result = state.results[item.caseId]; if (!result) return "未生成"; if (result.error) return "生成失败"; if (result.score?.passed === true) return "自动通过"; return result.score?.tags?.includes("format_noise") ? "格式需复核" : "需人工复核"; }
    function renderCaseList() { const list = $("case-list"); list.replaceChildren(); const items = visibleCases(); $("visible-case-count").textContent = `${items.length} 个`; if (!items.length) { const empty = document.createElement("div"); empty.className = "empty-state"; empty.textContent = "当前筛选没有测试例。"; list.append(empty); return; } items.forEach((item) => { const row = document.createElement("button"); row.type = "button"; row.className = `case-row${item.caseId === state.selectedCaseId ? " active" : ""}`; const gameState = item.gameState || {}; row.innerHTML = `<div class="case-top"><span class="case-id">${item.caseId}</span><span class="case-kind">${categoryLabel(item)}</span></div><div class="case-title">${roleNames[item.npcId] || item.displayName || item.npcId}</div><div class="case-meta"><span>${stageLabels[item.relationshipStage] || item.relationshipStage}</span><span>·</span><span>${item.channel === "remote" ? "远程" : "当面"}</span><span>·</span><span>${gameState.location || "地点未设"}</span><span>·</span><span>${resultStatus(item)}</span>${item.history?.length ? "<span>·</span><span>续聊</span>" : ""}</div>`; row.addEventListener("click", () => selectCase(item)); list.append(row); }); }
    function renderTerms(container, terms, forbidden) { container.replaceChildren(); if (!terms.length) { const empty = document.createElement("span"); empty.className = "term empty"; empty.textContent = "未设置"; container.append(empty); return; } terms.forEach((term) => { const pill = document.createElement("span"); pill.className = `term${forbidden ? " forbidden" : ""}`; pill.textContent = term; container.append(pill); }); }
    function formatUsage(usage) { if (!usage || ![usage.inputTokens,usage.outputTokens,usage.totalTokens].some((value)=>Number.isInteger(value))) return "用量未返回"; const parts=[]; if (Number.isInteger(usage.inputTokens)) parts.push(`输入 ${usage.inputTokens}`); if (Number.isInteger(usage.outputTokens)) parts.push(`输出 ${usage.outputTokens}`); if (Number.isInteger(usage.totalTokens)) parts.push(`合计 ${usage.totalTokens}`); return `Token：${parts.join(" / ")}`; }
    function formatCost(cost) { if (!cost || !Number.isFinite(Number(cost.amount))) return "费用未配置"; return `估算费用：¥${Number(cost.amount).toFixed(4)}`; }
    function plannedTurns(item) { const turns=Array.isArray(item.turns)&&item.turns.length?item.turns:[{turnId:"turn-1",playerInput:item.playerInput||""}]; return turns; }
    function caseUsage(result) { const turns=Array.isArray(result?.turns)?result.turns:[]; const usage={inputTokens:0,outputTokens:0,totalTokens:0}; let count=0; turns.forEach((turn)=>{ if(!turn?.usage)return; count+=1; ["inputTokens","outputTokens","totalTokens"].forEach((key)=>{if(Number.isInteger(turn.usage[key]))usage[key]+=turn.usage[key];}); }); return count?{...usage,count}:null; }
    function renderCaseTranscript(container, item) { const result=state.results[item.caseId]||{}; const definitions=plannedTurns(item); const resultTurns=Array.isArray(result.turns)?result.turns:[]; const count=Math.max(definitions.length,resultTurns.length,1); const card=document.createElement("section"); card.className="transcript-card"; const header=document.createElement("div"); header.className="transcript-card-header"; const heading=document.createElement("strong"); heading.textContent="完整连续对话 · 实际生成回复"; const status=document.createElement("span"); status.className="result-status"; status.textContent=resultStatus(item); header.append(heading,status); card.append(header); const usage=caseUsage(result); const summary=document.createElement("div"); summary.className="transcript-summary"; summary.textContent=`${count} 轮 · ${resultTurns.length?`${resultTurns.length} 轮已返回`:`尚未生成`} · ${usage?formatUsage(usage):"用量未返回"}`; card.append(summary); if(Array.isArray(item.history)&&item.history.length){ const history=document.createElement("div"); history.className="transcript-history"; const historyTitle=document.createElement("div"); historyTitle.className="transcript-history-title"; historyTitle.textContent="预置上下文"; history.append(historyTitle); item.history.forEach((message)=>{ const line=document.createElement("div"); line.className="transcript-history-line"; const role=document.createElement("b"); role.textContent=message.role==="assistant"?"NPC":"玩家"; line.append(role,document.createTextNode(`　${message.content||""}`)); history.append(line); }); card.append(history); } for(let index=0;index<count;index+=1){ const definition=definitions[index]||{}; const turn=resultTurns[index]||{}; const turnCard=document.createElement("article"); turnCard.className="transcript-turn"; if(turn.error)turnCard.classList.add("error"); else if(turn.score?.passed===false)turnCard.classList.add("review"); const turnHead=document.createElement("div"); turnHead.className="transcript-turn-head"; const turnTitle=document.createElement("span"); turnTitle.textContent=`第 ${index+1} 轮 · ${turn.turnId||definition.turnId||`turn-${index+1}`}`; const turnState=document.createElement("span"); turnState.className="transcript-turn-state"; turnState.textContent=turn.reply?"已生成":turn.error?"失败":"待生成"; if(!turn.reply&&!turn.error)turnState.classList.add("ready"); turnHead.append(turnTitle,turnState); turnCard.append(turnHead); const playerLabel=document.createElement("div"); playerLabel.className="transcript-turn-label"; playerLabel.textContent="玩家"; const player=document.createElement("div"); player.className="transcript-turn-player"; player.textContent=turn.playerInput||definition.playerInput||"未设置"; turnCard.append(playerLabel,player); const npcLabel=document.createElement("div"); npcLabel.className="transcript-turn-label"; npcLabel.textContent="NPC"; const reply=document.createElement("div"); reply.className="transcript-turn-reply"; if(turn.reply)reply.textContent=turn.reply; else if(turn.error)reply.textContent=`生成失败：${turn.error}`; else {reply.classList.add("pending");reply.textContent="本轮尚未生成实际回复。";} turnCard.append(npcLabel,reply); const meta=document.createElement("div"); meta.className="transcript-turn-meta"; meta.textContent=[turn.provider?`Provider：${turn.provider}`:"Provider：未记录",turn.latencyMs!==undefined?`延迟：${turn.latencyMs} ms`:"延迟：—",formatUsage(turn.usage)].join(" · "); turnCard.append(meta); const score=turn.score||{}; const scoreParts=[]; if(score.expectedHits!==undefined)scoreParts.push(`话题证据 ${score.expectedHits}`); if(score.exactExpectedHits!==undefined)scoreParts.push(`精确命中 ${score.exactExpectedHits}`); if(score.forbiddenHits!==undefined)scoreParts.push(`禁用词 ${score.forbiddenHits}`); if(Array.isArray(score.tags)&&score.tags.length)scoreParts.push(`标签：${score.tags.join("、")}`); if(scoreParts.length){const scoreLine=document.createElement("div");scoreLine.className="transcript-turn-score";scoreLine.textContent=scoreParts.join(" · ");turnCard.append(scoreLine);} card.append(turnCard); } if(result?.error&&!resultTurns.length){ const empty=document.createElement("div"); empty.className="transcript-empty"; empty.textContent=`生成失败：${result.error}`; card.append(empty); } container.append(card); }
    function renderCaseResult(container, item) { renderCaseTranscript(container, item); }
    function renderCaseDetail() { const item = state.cases.find((candidate) => candidate.caseId === state.selectedCaseId) || state.cases[0]; const container = $("case-detail"); container.replaceChildren(); if (!item) { const empty = document.createElement("div"); empty.className = "empty-state"; empty.textContent = "暂无可显示的测试例。"; container.append(empty); return; } state.selectedCaseId = item.caseId; $("coverage-current").textContent = item.caseId; const gameState = item.gameState || {}; const title = document.createElement("div"); title.className = "detail-heading"; title.innerHTML = `<div><h2>${roleNames[item.npcId] || item.displayName || item.npcId}</h2><p>${item.caseId} · ${categoryLabel(item)} · 来源：${(item.sourceMods || []).join("、") || "未标注"}</p></div><span class="case-status">${resultStatus(item)}</span>`; container.append(title); const strip = document.createElement("div"); strip.className = "context-strip"; [["关系",stageLabels[item.relationshipStage] || item.relationshipStage],["渠道",channelLabels[item.channel] || item.channel],["预置历史",`${(item.history || []).length} 条`],["角色 ID",item.npcId]].forEach(([label,value]) => { const chip = document.createElement("span"); chip.className = "context-chip"; chip.innerHTML = `<b>${label}</b>${value}`; strip.append(chip); }); container.append(strip); const scene = document.createElement("div"); scene.className = "detail-block"; scene.innerHTML = '<h3>场景条件</h3><div class="scene-grid" id="scene-facts"></div><div class="story-progress" id="story-progress"><b>剧情进度</b></div>'; container.append(scene); const sceneLabels = {season:"季节",date:"日期",weather:"天气",time:"时间",location:"地点",friendshipHearts:"好感度"}; const sceneFacts = $("scene-facts"); Object.entries(sceneLabels).forEach(([key,label]) => { const fact = document.createElement("div"); fact.className = "scene-fact"; const value = gameState[key] ?? "未设置"; fact.innerHTML = `<span class="scene-label">${label}</span><span class="scene-value">${value}</span>`; sceneFacts.append(fact); }); $("story-progress").append(document.createTextNode(item.storyProgress || "未设置")); const prompt = document.createElement("div"); prompt.className = "prompt-card"; prompt.innerHTML = `<div><div class="prompt-label">玩家输入</div><div class="prompt-text">“${item.playerInput || ""}”</div></div><div class="goal"><strong>本例的用途</strong><p>检查角色在${stageLabels[item.relationshipStage] || item.relationshipStage}阶段，通过${channelLabels[item.channel] || item.channel}回答当前话题，并保持可追溯的上下文边界。</p></div>`; container.append(prompt); renderCaseResult(container, item); const expected = document.createElement("div"); expected.className = "detail-block"; expected.innerHTML = '<h3>期望出现的当前话题证据（用于自动评测提示）</h3><div class="term-row" id="expected-terms"></div>'; container.append(expected); renderTerms($("expected-terms"), item.expectedTerms || [], false); if ((item.forbiddenTerms || []).length) { const forbidden = document.createElement("div"); forbidden.className = "detail-block"; forbidden.innerHTML = '<h3>禁止提前引入或机械化的表达</h3><div class="term-row" id="forbidden-terms"></div>'; container.append(forbidden); renderTerms($("forbidden-terms"), item.forbiddenTerms || [], true); } const history = document.createElement("div"); history.className = "detail-block"; history.innerHTML = "<h3>预置上下文</h3>"; const historyBox = document.createElement("div"); historyBox.className = "history"; if (item.history?.length) item.history.forEach((message) => { const line = document.createElement("div"); line.innerHTML = `<b>${message.role === "assistant" ? "NPC" : "玩家"}</b>　${message.content}`; historyBox.append(line); }); else historyBox.textContent = "无预置历史：这是独立首轮测试。"; history.append(historyBox); container.append(history); const actions = document.createElement("div"); actions.className = "case-detail-actions"; actions.innerHTML = '<button class="btn gold" type="button" data-open-case-chat="true">带入聊天验证这一例</button>'; actions.querySelector("[data-open-case-chat]").addEventListener("click", () => { selectCase(item, true); }); container.append(actions); const provenance = document.createElement("div"); provenance.className = "provenance"; provenance.textContent = "来源：bridge/src/stardew_ai_bridge/character_quality_eval.py · DEFAULT_CASES；本轮结果来自脱敏质量评测工件。此页不展示完整 prompt，也不把案例字段自动发送给模型。"; container.append(provenance); }
    function renderBars(container, counts, labels) { container.replaceChildren(); const max = Math.max(...Object.values(counts), 1); Object.entries(counts).forEach(([key,value]) => { const row = document.createElement("div"); row.className = "bar-row"; row.innerHTML = `<span>${labels[key] || key}</span><span class="bar"><i style="width:${Math.round(value / max * 100)}%"></i></span><b>${value}</b>`; container.append(row); }); }
    function renderCoverage() { const roles = new Set(state.cases.map((item) => item.npcId)); const history = state.cases.filter((item) => item.history?.length).length; const channels = new Set(state.cases.map((item) => item.channel)); const sceneKeys = ["season","date","weather","time","location","friendshipHearts"]; const completeScenes = state.cases.filter((item) => sceneKeys.every((key) => item.gameState && item.gameState[key] !== undefined)).length; $("coverage-total").textContent = state.cases.length; $("coverage-roles").textContent = roles.size; $("coverage-history").textContent = `${history} / ${state.cases.length}`; $("coverage-channels").textContent = [...channels].map((item) => channelLabels[item] || item).join("、"); $("coverage-scenes").textContent = `${completeScenes} / ${state.cases.length}`; const summary=state.run?.summary||{}; const plannedTurns=state.cases.reduce((total,item)=>total+(Array.isArray(item.turns)?item.turns.length:1),0); $("coverage-turns").textContent = summary.turnCount!==undefined?`${summary.turnCount} 轮（${summary.successfulTurns??0} 轮成功）`:`${plannedTurns} 轮待生成`; const usage=summary.usage; $("coverage-tokens").textContent = usage&&Number.isInteger(usage.totalTokens)?`${usage.totalTokens} tokens（${usage.usageReturnedTurns??0} 轮有返回，${usage.missingUsageTurns??0} 轮无用量）`:"用量未返回"; $("coverage-cost").textContent = formatCost(summary.estimatedCost); const stages = {}; const channelCounts = {}; state.cases.forEach((item) => { stages[item.relationshipStage] = (stages[item.relationshipStage] || 0) + 1; channelCounts[item.channel] = (channelCounts[item.channel] || 0) + 1; }); renderBars($("stage-bars"), stages, stageLabels); renderBars($("channel-bars"), channelCounts, {remote:"远程",face_to_face:"当面"}); }
    async function loadQualityResults() { try { const response = await fetch("/api/quality/results"); if (!response.ok) throw new Error("质量结果接口不可用"); const payload = await response.json(); const results = Array.isArray(payload.results) ? payload.results : []; const resultByCaseId = Object.fromEntries(results.filter((item) => item && item.caseId).map((item) => [item.caseId, item])); state.run = payload; state.results = resultByCaseId; } catch (_) { state.run = null; state.results = {}; } }
    function batchProviderLabel(provider) { return {cloud:"云端（显式）",local:"本地 qwen3.5:9b",fake:"Fake 演示"}[provider] || provider || "未知 Provider"; } function renderBatchSummary() { const summary = state.run?.summary || {}; const results = Object.keys(state.results).length; if (state.run?.batchId) { $("batch-title").textContent = `本轮生成 · ${state.run.batchId}`; const usage=summary.usage; const tokenText=usage&&Number.isInteger(usage.totalTokens)?` · ${usage.totalTokens} tokens`:" · 用量未返回"; $("batch-summary").textContent = `${results} 条实际结果 · ${summary.successful ?? results} 个案例返回 · ${summary.turnCount ?? "—"} 轮${tokenText}`; const providers = [...new Set(Object.values(state.results).flatMap((item) => Array.isArray(item?.turns)?item.turns.map((turn)=>turn?.provider):[item?.provider]).filter(Boolean))]; $("batch-run-status").textContent = `${providers.length ? `来源：${providers.map(batchProviderLabel).join("、")}` : "来源：未记录 Provider"} · ${formatCost(summary.estimatedCost)}`; } else { $("batch-title").textContent = "固定角色场景"; $("batch-summary").textContent = `${state.cases.length} 个案例 · 尚未接入生成结果`; $("batch-run-status").textContent = ""; } }
    async function loadQualityCases() { try { const response = await fetch("/api/quality/cases"); if (!response.ok) throw new Error("测试例接口不可用"); const payload = await response.json(); state.cases = Array.isArray(payload.cases) ? payload.cases : []; await loadQualityResults(); renderBatchSummary(); renderFilterCounts(); renderCoverage(); renderCaseList(); renderCaseDetail(); if (state.cases[0]) window.setTimeout(() => selectCase(state.cases[0]), 0); } catch (error) { $("case-list").innerHTML = `<div class="empty-state">${error.message}</div>`; $("case-detail").innerHTML = `<div class="empty-state">无法加载测试例目录。<br>请检查 Bridge 是否在线。</div>`; } }
    function applyCaseFilter(filter) { state.filter = filter; $$(".filter-btn").forEach((button) => button.classList.toggle("active", button.dataset.filter === filter)); renderCaseList(); if (!visibleCases().some((item) => item.caseId === state.selectedCaseId)) { state.selectedCaseId = visibleCases()[0]?.caseId || ""; renderCaseDetail(); } }
    function $$(selector) { return [...document.querySelectorAll(selector)]; }
    $$(".filter-btn").forEach((button) => button.addEventListener("click", () => applyCaseFilter(button.dataset.filter))); $("show-all").addEventListener("click", () => applyCaseFilter("all")); $("export-case").addEventListener("click", () => showToast(state.selectedCaseId ? `已模拟导出 ${state.selectedCaseId}` : "请先选择一个测试例"));
    async function loadHealth() { try { const response = await fetch("/health"); const data = await response.json(); $("health").textContent = `Bridge 在线 · ${data.provider}`; } catch (_) { $("health").textContent = "Bridge 不可用"; } }
    loadQualityCases(); loadHealth();
  </script>
</body>
</html>
"""


RAW_DIALOGUE_REFERENCE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stardew AI NPC · 原始对白参照</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
      --ink:#33281f; --muted:#79695c; --line:#ddc9b3; --paper:#fffaf3; --strong:#fffdf9;
      --accent:#9b5b42; --accent-dark:#6e3c2e; --accent-soft:#f3dfd0; --good:#52745a; --warn:#946b2f; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:#f2e8dc; color:var(--ink); }
    button,input,select { font:inherit; }
    button { border:1px solid var(--accent-dark); border-radius:9px; background:var(--accent); color:#fff; cursor:pointer; padding:9px 13px; }
    button:hover { background:var(--accent-dark); }
    button.secondary { background:var(--strong); color:var(--accent-dark); border-color:var(--line); }
    button.secondary:hover { background:var(--accent-soft); }
    input,select { width:100%; border:1px solid var(--line); border-radius:8px; background:var(--strong); color:var(--ink); padding:9px 10px; }
    input:focus,select:focus,button:focus-visible { outline:3px solid #e8b58f; outline-offset:1px; }
    .app { max-width:1500px; height:100vh; margin:0 auto; padding:24px; display:flex; flex-direction:column; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:18px; }
    .title { margin:0; font-size:clamp(1.45rem,2.4vw,2.1rem); letter-spacing:.02em; }
    .subtitle { margin:7px 0 0; color:var(--muted); font-size:.92rem; line-height:1.5; }
    .top-actions { display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }
    .back-link { display:inline-flex; align-items:center; padding:9px 13px; border:1px solid var(--line); border-radius:9px; background:var(--strong); color:var(--accent-dark); text-decoration:none; font-size:.84rem; }
    .back-link:hover { background:var(--accent-soft); }
    .health { display:inline-flex; align-items:center; gap:7px; padding:8px 11px; border:1px solid var(--line); border-radius:99px; background:var(--paper); color:var(--muted); font-size:.84rem; }
    .health::before { content:""; width:8px; height:8px; border-radius:50%; background:var(--warn); }
    .health.ready { color:var(--good); }
    .health.ready::before { background:var(--good); }
    .panel { border:1px solid var(--line); border-radius:14px; background:var(--paper); box-shadow:0 10px 28px #6c4a3214; }
    .toolbar { padding:18px; }
    .toolbar-grid { display:grid; grid-template-columns:minmax(220px,280px) minmax(0,1fr); gap:16px; align-items:end; }
    label { display:grid; gap:6px; color:var(--muted); font-size:.82rem; }
    .quick-switch { display:grid; gap:7px; }
    .quick-switch-label { color:var(--muted); font-size:.78rem; }
    .npc-buttons { display:flex; flex-wrap:wrap; gap:7px; }
    .npc-switch { padding:7px 11px; background:var(--strong); color:var(--accent-dark); border-color:var(--line); font-size:.8rem; }
    .npc-switch:hover,.npc-switch.active { background:var(--accent); color:#fff; border-color:var(--accent-dark); }
    .filter-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; align-items:end; margin-top:16px; }
    .raw-dialogue-count { color:var(--muted); font-size:.82rem; line-height:1.45; }
    .reference-grid { display:grid; flex:1; min-height:0; grid-template-columns:minmax(320px,.82fr) minmax(0,1.6fr); grid-template-rows:minmax(0,1fr); gap:16px; margin-top:16px; }
    .reference-section { min-width:0; min-height:0; display:flex; flex-direction:column; overflow:hidden; padding:18px; }
    .section-heading { display:flex; justify-content:space-between; align-items:baseline; gap:10px; padding-bottom:10px; border-bottom:1px solid #eadbca; }
    .section-heading h2 { margin:0; color:var(--accent-dark); font-size:1rem; }
    .section-note { color:var(--muted); font-size:.75rem; }
    .reference-section .raw-dialogue-list { display:grid; flex:1; min-height:0; gap:10px; max-height:none; overflow-y:auto; overflow-x:hidden; padding:12px 3px 3px 0; }
    .raw-entry { padding:11px 12px; border:1px solid #eadbca; border-radius:10px; background:var(--strong); }
    .raw-entry.pinned { border-color:#c9956e; background:#fff5e9; }
    .raw-entry-meta { color:var(--muted); font-size:.72rem; line-height:1.45; }
    .raw-entry-text { margin-top:6px; white-space:pre-wrap; overflow-wrap:anywhere; font-size:.88rem; line-height:1.6; }
    .raw-entry-source { margin-top:7px; color:var(--muted); font-size:.68rem; overflow-wrap:anywhere; }
    .raw-empty { padding:20px 8px; color:var(--muted); font-size:.82rem; line-height:1.5; }
    .footnote { margin:16px 2px 0; color:var(--muted); font-size:.76rem; line-height:1.5; }
    @media (max-width:850px) { body { overflow:auto; } .app { height:auto; min-height:100vh; padding:12px; display:block; } .topbar { align-items:stretch; flex-direction:column; } .top-actions { justify-content:flex-start; } .toolbar-grid,.reference-grid { grid-template-columns:1fr; } .reference-grid { grid-template-rows:repeat(2,minmax(320px,auto)); } .filter-row { grid-template-columns:1fr; } .reference-section .raw-dialogue-list { min-height:240px; } }
  </style>
</head>
<body>
  <main class="app" id="raw-dialogue-page">
    <header class="workspace-topbar topbar">
      <div class="workspace-brand brand"><div class="workspace-mark mark">✦</div><div><div class="workspace-eyebrow eyebrow">Stardew AI NPC · Dialogue Lab</div><strong>原始对白参照</strong><p class="workspace-subtitle subtitle">查看已解析原文，作为角色语气的人工参照。</p></div></div>
      <nav class="workspace-nav" aria-label="工作台导航"><a class="workspace-tab" href="/test">测试例浏览</a><a class="workspace-tab" href="/test/chat">单次聊天</a><a class="workspace-tab" href="/raw" aria-current="page">原始对白</a></nav>
      <div class="top-actions"><span id="health" class="health">Bridge 检查中……</span><a class="back-link" href="/test">返回测试例浏览</a></div>
    </header>
    <section class="panel toolbar">
      <div class="toolbar-grid">
        <label>NPC<select id="npc-select"></select></label>
        <div class="quick-switch"><span class="quick-switch-label">快速查看评测角色</span><div id="npc-buttons" class="npc-buttons" role="group" aria-label="快速查看评测角色"></div></div>
      </div>
      <div class="filter-row"><label>筛选原文<input id="raw-dialogue-filter" type="search" placeholder="搜索文本、来源、sourceKey 或关系条件"></label><div class="raw-dialogue-count" id="raw-dialogue-count">正在加载当前角色的已解析原文……</div></div>
    </section>
    <div class="reference-grid">
      <section class="panel reference-section"><div class="section-heading"><h2>置顶代表对白</h2><span class="section-note">最多 16 条</span></div><div id="raw-dialogue-representatives" class="raw-dialogue-list" aria-live="polite"><div class="raw-empty">正在加载……</div></div></section>
      <section class="panel reference-section"><div class="section-heading"><h2>全部原始对白</h2><span class="section-note">保留来源和条件</span></div><div id="raw-dialogue-list" class="raw-dialogue-list" aria-live="polite"><div class="raw-empty">正在加载……</div></div></section>
    </div>
    <p class="footnote">这里展示的是“已解析原文”，部分婚后、事件、节日或 Content Patcher 文本会保留原始控制标记，便于审计；它们不会自动进入聊天生成请求。</p>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const EVALUATION_NPC_IDS = ["Wizard", "Sophia", "Shane", "Sebastian", "Alex"];
    const EVALUATION_LABELS = {Wizard:"Rasmodia / Wizard",Sophia:"Sophia",Shane:"Shane",Sebastian:"Sebastian",Alex:"Alex"};
    const state = {npcs:[],activeNpcId:"Wizard",rawDialogue:{npcId:"",total:0,representatives:[],dialogues:[]}};
    function canonicalNpcId(npcId){const value=typeof npcId==="string"?npcId.trim():"";return ["wizard","rasmodia"].includes(value.toLowerCase())?"Wizard":value;}
    function rawDialogueMatches(item){const query=$("raw-dialogue-filter").value.trim().toLocaleLowerCase();if(!query)return true;return [item.text,item.sourceMod,item.sourcePath,item.sourceKey,JSON.stringify(item.conditions||{})].some((value)=>String(value||"").toLocaleLowerCase().includes(query));}
    function renderRawDialogueList(container,items,emptyText,pinned=false){container.replaceChildren();if(!items.length){const empty=document.createElement("div");empty.className="raw-empty";empty.textContent=emptyText;container.append(empty);return;}for(const item of items){const entry=document.createElement("article");entry.className=`raw-entry ${pinned?"pinned":""}`;const meta=document.createElement("div");meta.className="raw-entry-meta";const condition=Object.entries(item.conditions||{}).map(([key,value])=>`${key}=${value}`).join("；");meta.textContent=[pinned?"置顶参照":"原文",item.sourceMod||"未知来源",item.sourceKey||"未标注",condition].filter(Boolean).join(" · ");const body=document.createElement("div");body.className="raw-entry-text";body.textContent=item.text||"";const source=document.createElement("div");source.className="raw-entry-source";source.textContent=`来源文件：${item.sourcePath||"未记录"}`;entry.append(meta,body,source);container.append(entry);}}
    function renderRawDialogue(){const data=state.rawDialogue||{};const dialogues=Array.isArray(data.dialogues)?data.dialogues:[];const representatives=Array.isArray(data.representatives)?data.representatives:[];const filtered=dialogues.filter(rawDialogueMatches);const filteredRepresentatives=representatives.filter(rawDialogueMatches);$("raw-dialogue-count").textContent=`当前角色共 ${data.total||0} 条已解析原文，筛选后显示 ${filtered.length} 条。`;renderRawDialogueList($("raw-dialogue-representatives"),filteredRepresentatives,"当前筛选没有置顶参照。",true);renderRawDialogueList($("raw-dialogue-list"),filtered,"当前筛选没有原始对白。",false);}
    function selectNpc(npcId){const canonicalId=canonicalNpcId(npcId);state.activeNpcId=canonicalId;window.dispatchEvent(new CustomEvent("dialogue-lab:npc-selected",{detail:{npcId:canonicalId,displayName:EVALUATION_LABELS[canonicalId]||canonicalId,source:"raw"}}));renderQuickButtons();}
    async function loadRawDialogue(npcId){const canonicalId=canonicalNpcId(npcId);selectNpc(canonicalId);state.rawDialogue={npcId:canonicalId,total:0,representatives:[],dialogues:[]};renderRawDialogue();try{const response=await fetch(`/api/dialogue/raw?npcId=${encodeURIComponent(npcId)}`);if(!response.ok)throw new Error("原始对白加载失败");const data=await response.json();state.rawDialogue={npcId:canonicalNpcId(data.npcId||npcId),total:Number.isFinite(data.total)?data.total:0,representatives:Array.isArray(data.representatives)?data.representatives:[],dialogues:Array.isArray(data.dialogues)?data.dialogues:[]};renderRawDialogue();}catch(error){state.rawDialogue={npcId:canonicalId,total:0,representatives:[],dialogues:[]};renderRawDialogue();$("raw-dialogue-count").textContent=`原始对白加载失败：${error.message}`;}}
    function renderQuickButtons(){const container=$("npc-buttons");container.replaceChildren();for(const npcId of EVALUATION_NPC_IDS){const button=document.createElement("button");button.type="button";button.className=`npc-switch ${npcId===state.activeNpcId?"active":""}`;button.textContent=EVALUATION_LABELS[npcId];button.setAttribute("aria-pressed",String(npcId===state.activeNpcId));button.addEventListener("click",()=>{const select=$("npc-select");if(Array.from(select.options).some((option)=>option.value===npcId))select.value=npcId;loadRawDialogue(npcId);});container.append(button);}}
    async function loadNpcs(){const response=await fetch("/api/npcs");if(!response.ok)throw new Error("NPC 资料加载失败");state.npcs=(await response.json()).npcs||[];const select=$("npc-select");select.replaceChildren();for(const npc of state.npcs){const option=document.createElement("option");option.value=npc.npcId;option.textContent=`${npc.displayName} (${npc.npcId})`;select.append(option);}select.value="Wizard";select.addEventListener("change",()=>loadRawDialogue(select.value));renderQuickButtons();await loadRawDialogue(select.value);}
    async function loadHealth(){try{const response=await fetch("/health");const data=await response.json();if(!response.ok)throw new Error();$("health").textContent=`Bridge 在线 · ${data.provider}`;$("health").classList.add("ready");}catch(_){$("health").textContent="Bridge 不可用";}}
    $("raw-dialogue-filter").addEventListener("input",renderRawDialogue);renderQuickButtons();Promise.all([loadNpcs(),loadHealth()]).catch((error)=>$("raw-dialogue-count").textContent=error.message);
  </script>
</body>
</html>
"""


DIALOGUE_LAB_SHARED_UI_CSS = """
    :root {
      --ui-shell-version: 4;
      --ink:#2f382f; --muted:#6f7e72; --line:#d5dfd5; --paper:#fffef9; --strong:#ffffff;
      --accent:#3f7054; --accent-dark:#2b563d; --accent-soft:#e8f2e9;
      --npc:#eef6ed; --player:#eaf1f7; --good:#52745a; --warn:#946b2f;
      --green:#3f7054; --green-soft:#e8f2e9; --gold:#b37c2d; --gold-soft:#fff1d7;
      --rose:#a45550; --rose-soft:#f8e8e5; --shadow:0 12px 30px #3d5d4614;
    }
    body { background:#e8eee8; color:var(--ink); }
    .workspace-topbar {
      display:grid; grid-template-columns:minmax(220px,1fr) auto auto; align-items:center; gap:16px;
      flex:0 0 auto; margin-bottom:12px; padding:11px 14px; border-radius:13px;
      color:#f9faf4; background:linear-gradient(110deg,#294b3b,#3c6b52); box-shadow:4px 4px 15px #244a351f;
    }
    .workspace-brand { display:flex; align-items:center; gap:10px; min-width:220px; }
    .workspace-mark { width:31px; height:31px; display:grid; place-items:center; flex:0 0 auto; border:1px solid #ffffff3d; border-radius:9px; color:#f1d085; background:#ffffff12; font-size:17px; }
    .workspace-eyebrow { color:#d6e4d6; font-size:9px; letter-spacing:.13em; text-transform:uppercase; }
    .workspace-brand strong { display:block; margin-top:2px; color:#fff; font-size:14px; }
    .workspace-subtitle { margin:3px 0 0; color:#d6e4d6; font-size:10px; }
    .workspace-nav { display:flex; align-items:center; gap:4px; min-width:0; }
    .workspace-tab { padding:8px 12px; border:0; border-radius:7px; color:#d5e3d5; background:transparent; text-decoration:none; font-size:12px; white-space:nowrap; }
    .workspace-tab:hover, .workspace-tab[aria-current="page"] { color:#fff; background:#ffffff19; }
    .workspace-topbar .top-meta, .workspace-topbar .top-actions { display:flex; align-items:center; flex-wrap:wrap; justify-content:flex-end; gap:8px; margin-left:0; color:#d7e5d8; font-size:10px; }
    .workspace-topbar .prototype { color:#f0cd82; }
    .workspace-topbar .health { display:inline-flex; align-items:center; gap:6px; padding:6px 9px; border:1px solid #ffffff27; border-radius:20px; background:#17382735; color:#d7e5d8; }
    .workspace-topbar .health::before { content:""; width:7px; height:7px; border-radius:50%; background:#e0b85f; }
    .workspace-topbar .health.ready { color:#dcf0dd; }
    .workspace-topbar .health.ready::before { background:#90d19b; }
    .workspace-topbar .secondary-link, .workspace-topbar .back-link { display:inline-flex; align-items:center; padding:7px 10px; border:1px solid #ffffff38; border-radius:8px; color:#eff8ef; background:#ffffff12; text-decoration:none; font-size:10px; }
    .workspace-topbar .secondary-link:hover, .workspace-topbar .back-link:hover { background:#ffffff21; }
    .workspace-topbar button.secondary { padding:7px 10px; border-color:#ffffff38; border-radius:8px; color:#eff8ef; background:#ffffff12; font-size:10px; }
    .workspace-topbar button.secondary:hover { background:#ffffff21; }
    .workspace-topbar + .heading .heading-actions .btn, .workspace-topbar ~ .btn { border-color:var(--line); color:var(--ink); background:#ffffffd9; }
    .workspace-topbar + .heading .heading-actions .btn:hover { border-color:#9cbaa4; background:#fff; }
    #dialogue-lab-workspace .workspace-view { color:var(--ink); font-size:12px; }
    #dialogue-lab-workspace .workspace-view .panel { border:1px solid var(--line); border-radius:13px; background:var(--paper); box-shadow:var(--shadow); }
    #dialogue-lab-workspace .workspace-view .panel-header { display:flex; align-items:center; justify-content:space-between; min-height:45px; height:auto; padding:0 13px; border-bottom:1px solid var(--line); background:#fafcf8; }
    #dialogue-lab-workspace .workspace-view .panel-header h2 { margin:0; color:var(--ink); font-size:13px; }
    #dialogue-lab-workspace .workspace-view .panel-body { padding:12px 13px; }
    #dialogue-lab-workspace .workspace-view input,
    #dialogue-lab-workspace .workspace-view select,
    #dialogue-lab-workspace .workspace-view textarea { border-color:var(--line); border-radius:8px; background:var(--strong); color:var(--ink); font-size:11px; }
    #dialogue-lab-workspace .workspace-view button { transition:background .15s ease, border-color .15s ease, color .15s ease; }
    #dialogue-lab-workspace [data-workspace-view="chat"] .message { font-size:12px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="raw"] .raw-entry-text { font-size:12px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] {
      font-size:12px;
    }
    #dialogue-lab-workspace [data-workspace-view="cases"] .browser-layout {
      grid-template-columns:minmax(240px,.85fr) minmax(0,2fr) minmax(260px,.95fr);
      gap:12px;
    }
    #dialogue-lab-workspace [data-workspace-view="cases"] .panel-body,
    #dialogue-lab-workspace [data-workspace-view="chat"] .panel-body,
    #dialogue-lab-workspace [data-workspace-view="raw"] .reference-section { padding:12px 13px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-row { padding:8px 10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .filter-btn { padding:8px 10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-title { font-size:12px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-meta { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .scene-value { font-size:12px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .kicker { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .batch-card small { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .batch-card span { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .section-head strong { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .section-head span { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .filter-btn span { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-id,
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-kind { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .nav-note { font-size:11px; line-height:1.5; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-heading p { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-status,
    #dialogue-lab-workspace [data-workspace-view="cases"] .context-chip { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .scene-label { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .story-progress { font-size:12px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .story-progress b { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .prompt-label { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .goal strong { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .goal p { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-block h3 { font-size:13px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .term { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .history { font-size:12px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .history b { font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .provenance { font-size:10px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .coverage-intro { font-size:11px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .coverage-section h3 { font-size:13px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .metric { font-size:12px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .bar-row { font-size:11px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .gap-box { font-size:11px; line-height:1.55; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .gap-box strong { font-size:12px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .empty-state { font-size:12px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-panel .panel-body { line-height:1.5; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .prompt-card { min-height:92px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-row.high-affinity { border-color:#d8b56b; background:#fffaf0; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-row.high-affinity .case-kind { color:#9a6b22; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .context-chip.high-affinity { border-color:#e2c985; color:#8a6425; background:#fff8e7; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .style-quality-block { padding-top:2px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-tools { margin-top:12px; padding:9px; border:1px solid #e0e8df; border-radius:9px; background:#f8faf6; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:6px; align-items:end; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-label { display:block; color:#5f7064; font-size:9px; font-weight:700; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-input { display:flex; gap:5px; margin-top:4px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-input input { min-width:0; width:100%; padding:6px 7px; border:1px solid #d9e2d8; border-radius:6px; color:var(--ink); background:#fff; font-size:10px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-clear { padding:5px 7px; border:1px solid #d9e2d8; border-radius:6px; color:#68756b; background:#fff; font-size:9px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-search-clear:disabled { cursor:default; opacity:.45; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-filter-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:7px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-filter-grid label { display:grid; gap:3px; color:#738076; font-size:9px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-filter-grid select { width:100%; padding:5px 6px; border:1px solid #d9e2d8; border-radius:6px; color:var(--ink); background:#fff; font-size:9px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .review-filter { color:#896225; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-detail-toolbar { position:sticky; top:-14px; z-index:2; display:flex; align-items:center; justify-content:space-between; gap:8px; margin:-14px -15px 10px; padding:8px 15px; border-bottom:1px solid #dfe7de; background:#fffffff2; box-shadow:0 3px 8px #3d5d460b; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-position { color:#6d796f; font-size:10px; font-weight:700; white-space:nowrap; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:5px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-btn { padding:5px 7px; border:1px solid #d9e2d8; border-radius:6px; color:#4f6957; background:#fff; font-size:9px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-btn:hover { border-color:#9cbaa4; background:#f4faf3; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-btn:disabled { cursor:default; opacity:.42; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-btn.review { border-color:#e2c985; color:#896225; background:#fff8e7; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-block-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-section-toggle { flex:0 0 auto; padding:3px 6px; border:1px solid #d9e2d8; border-radius:5px; color:#5f7064; background:#fff; font-size:9px; font-weight:500; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-section-toggle:hover { border-color:#9cbaa4; background:#f4faf3; }
    #dialogue-lab-workspace [data-workspace-view="cases"] .detail-section-content[hidden] { display:none; }
    #dialogue-lab-workspace [data-workspace-view="chat"] .layout { gap:12px; }
    @media (max-width:1050px) {
      .workspace-topbar { grid-template-columns:minmax(0,1fr) auto; }
      .workspace-nav { grid-column:1 / -1; grid-row:2; justify-content:flex-start; overflow:auto; }
    }
    @media (max-width:700px) {
      body { overflow:auto; }
      .app { height:auto; min-height:100vh; }
      .layout, .browser-layout, .reference-grid { grid-template-columns:1fr; gap:8px; }
      .transcript-panel { min-height:60vh; }
      .workspace-topbar { grid-template-columns:1fr; gap:7px; align-items:start; padding:9px 10px; }
      .workspace-nav { grid-column:auto; grid-row:auto; width:100%; overflow:auto; }
      .workspace-topbar .top-meta, .workspace-topbar .top-actions { justify-content:flex-start; }
      .workspace-tab { padding:6px 8px; font-size:10px; }
    }
"""


_DIALOGUE_LAB_SOURCE_HTML = DIALOGUE_LAB_HTML
_DIALOGUE_CASE_BROWSER_SOURCE_HTML = DIALOGUE_CASE_BROWSER_HTML
_RAW_DIALOGUE_REFERENCE_SOURCE_HTML = RAW_DIALOGUE_REFERENCE_HTML


def _with_shared_ui(html: str) -> str:
    """给三个实验室页面注入共同主题，并标记同一套工作台壳层版本。"""

    themed = html.replace("</style>", f"{DIALOGUE_LAB_SHARED_UI_CSS}\n  </style>", 1)
    return themed.replace("<main ", '<main data-ui-shell="v4" ', 1)


DIALOGUE_LAB_HTML = _with_shared_ui(DIALOGUE_LAB_HTML)
DIALOGUE_CASE_BROWSER_HTML = _with_shared_ui(DIALOGUE_CASE_BROWSER_HTML)
RAW_DIALOGUE_REFERENCE_HTML = _with_shared_ui(RAW_DIALOGUE_REFERENCE_HTML)


def _extract_main_inner(html: str) -> str:
    match = re.search(r"<main\b[^>]*>(.*?)</main>", html, flags=re.DOTALL | re.IGNORECASE)
    if match is None:
        raise ValueError("页面缺少 main 容器")
    return re.sub(
        r"<header\b.*?</header>\s*",
        "",
        match.group(1),
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()


def _extract_style(html: str) -> str:
    match = re.search(r"<style>(.*?)</style>", html, flags=re.DOTALL | re.IGNORECASE)
    if match is None:
        raise ValueError("页面缺少 style 容器")
    return match.group(1)


def _extract_script(html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL | re.IGNORECASE)
    if not scripts:
        raise ValueError("页面缺少 script 容器")
    return scripts[-1]


def _extract_case_toast(html: str) -> str:
    match = re.search(
        r'<div class="toast" id="toast".*?</div>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return match.group(0) if match else '<div class="toast" id="toast" role="status"></div>'


def _augment_case_browser_script(script: str) -> str:
    """为现有案例脚本补充阶段筛选和表达质量摘要。"""

    enhancement = r'''
    const relationshipStageLabel = stageLabels;
    const highAffinityStages = new Set(["close", "dating", "married", "parent"]);
    const caseFilterValues = new Set(["all", "daily", "channel", "continuity", "needs_review", "high_affinity", "stranger", "acquaintance", "friend", "close", "dating", "married", "parent"]);
    const caseStatusValues = new Set(["", "needs_review", "unrun", "passed", "error"]);
    state.query = "";
    state.roleFilter = "";
    state.statusFilter = "";
    function readCaseViewState() {
      const searchParams = new URLSearchParams(window.location.search);
      const filter = searchParams.get("filter");
      const status = searchParams.get("status");
      return {
        caseId: searchParams.get("case") || "",
        filter: caseFilterValues.has(filter) ? filter : "all",
        query: searchParams.get("q") || "",
        role: searchParams.get("role") || "",
        status: caseStatusValues.has(status) ? status : "",
      };
    }
    const initialCaseViewState = readCaseViewState();
    state.filter = initialCaseViewState.filter;
    state.query = initialCaseViewState.query;
    state.roleFilter = initialCaseViewState.role;
    state.statusFilter = initialCaseViewState.status;
    function updateCaseViewUrl() {
      const url = new URL(window.location.href);
      const searchParams = url.searchParams;
      if (state.selectedCaseId) searchParams.set("case", state.selectedCaseId); else searchParams.delete("case");
      if (state.filter && state.filter !== "all") searchParams.set("filter", state.filter); else searchParams.delete("filter");
      if (state.query) searchParams.set("q", state.query); else searchParams.delete("q");
      if (state.roleFilter) searchParams.set("role", state.roleFilter); else searchParams.delete("role");
      if (state.statusFilter) searchParams.set("status", state.statusFilter); else searchParams.delete("status");
      window.history.replaceState({}, "", url);
    }
    function caseMatchesSearch(item) {
      const haystack = [item.caseId, item.displayName, item.npcId, item.playerInput, item.storyProgress, item.channel, channelLabels[item.channel], item.relationshipStage, relationshipStageLabel[item.relationshipStage], ...(item.sourceMods || []), ...Object.values(item.gameState || {})].join(" ").toLocaleLowerCase();
      return !state.query || haystack.includes(state.query.toLocaleLowerCase());
    }
    function statusMatches(item, status = state.statusFilter) {
      if (!status) return true;
      const result = state.results[item.caseId];
      if (status === "unrun") return !result;
      if (status === "error") return Boolean(result?.error);
      if (status === "passed") return result?.score?.passed === true;
      if (status === "needs_review") return Boolean(result && !result.error && result.score?.passed !== true || result?.error);
      return true;
    }
    function matchesFilter(item) {
      const categoryMatches = state.filter === "needs_review"
        ? true
        : state.filter === "high_affinity"
          ? highAffinityStages.has(item.relationshipStage)
          : relationshipStageLabel[state.filter]
            ? item.relationshipStage === state.filter
            : state.filter === "all" || categoryOf(item) === state.filter;
      return categoryMatches
        && (state.filter !== "needs_review" || statusMatches(item, "needs_review"))
        && (!state.roleFilter || item.npcId === state.roleFilter)
        && statusMatches(item)
        && caseMatchesSearch(item);
    }
    function visibleCases() { return state.cases.filter((item) => matchesFilter(item)); }
    function populateCaseRoleFilter() {
      const select = $("case-role-filter");
      if (!select) return;
      const current = state.roleFilter;
      select.replaceChildren(new Option("全部角色", ""));
      const roles = [...new Set(state.cases.map((item) => item.npcId).filter(Boolean))];
      roles.forEach((npcId) => select.append(new Option(roleNames[npcId] || npcId, npcId)));
      state.roleFilter = roles.includes(current) ? current : "";
      select.value = state.roleFilter;
    }
    function syncCaseFilterControls() {
      const search = $("case-search");
      const role = $("case-role-filter");
      const status = $("case-status-filter");
      if (search && search.value !== state.query) search.value = state.query;
      if (role && role.value !== state.roleFilter) role.value = state.roleFilter;
      if (status && status.value !== state.statusFilter) status.value = state.statusFilter;
      $("case-search-clear")?.toggleAttribute("disabled", !state.query);
    }
    function selectFirstVisibleCaseIfNeeded() {
      if (visibleCases().some((item) => item.caseId === state.selectedCaseId)) return;
      state.selectedCaseId = visibleCases()[0]?.caseId || "";
    }
    function initialCaseForSelection() {
      return state.cases.find((item) => item.caseId === initialCaseViewState.caseId)
        || visibleCases()[0]
        || state.cases[0];
    }
    const baseRenderFilterCounts = renderFilterCounts;
    renderFilterCounts = function () {
      baseRenderFilterCounts();
      const counts = { needs_review: 0, high_affinity: 0, stranger: 0, acquaintance: 0, friend: 0, close: 0, dating: 0, married: 0, parent: 0 };
      state.cases.forEach((item) => {
        if (statusMatches(item, "needs_review")) counts.needs_review += 1;
        if (highAffinityStages.has(item.relationshipStage)) counts.high_affinity += 1;
        if (Object.prototype.hasOwnProperty.call(counts, item.relationshipStage)) counts[item.relationshipStage] += 1;
      });
      Object.entries(counts).forEach(([key, value]) => {
        const element = $(`filter-${key}-count`);
        if (element) element.textContent = value;
      });
    };
    const baseRenderCaseList = renderCaseList;
    renderCaseList = function () {
      baseRenderCaseList();
      visibleCases().forEach((item, index) => {
        const row = $("case-list").children[index];
        if (!row || !row.classList.contains("case-row")) return;
        row.dataset.caseId = item.caseId;
        const meta = row.querySelector(".case-meta");
        if (!meta) return;
        const heart = document.createElement("span");
        heart.textContent = `· ${item.gameState?.friendshipHearts ?? 0} 心`;
        meta.append(heart);
        if (highAffinityStages.has(item.relationshipStage)) row.classList.add("high-affinity");
      });
    };
    const baseRenderCoverage = renderCoverage;
    renderCoverage = function () {
      baseRenderCoverage();
      const highAffinity = state.cases.filter((item) => highAffinityStages.has(item.relationshipStage));
      const target = $("coverage-high-affinity");
      if (target) target.textContent = `${highAffinity.length} / ${state.cases.length}`;
    };
    function qualityTagLabel(tag) {
      return {
        repeated_speech_particle: "重复语气词",
        repeated_opening: "重复开场",
        too_many_speech_particles: "语气词过密",
      }[tag] || tag;
    }
    function renderStyleQualitySummary(container, item) {
      const block = document.createElement("div");
      block.className = "detail-block style-quality-block";
      block.innerHTML = "<h3>表达变化提示</h3>";
      const tags = new Set();
      const results = state.results[item.caseId] || {};
      [results.styleQuality, ...(Array.isArray(results.turns) ? results.turns.map((turn) => turn?.styleQuality) : [])]
        .filter(Boolean)
        .forEach((quality) => (quality.tags || []).forEach((tag) => tags.add(tag)));
      const row = document.createElement("div");
      row.className = "term-row";
      if (!tags.size) {
        const empty = document.createElement("span");
        empty.className = "term empty";
        empty.textContent = results.styleQuality ? "未发现提示" : "未检测（旧批次未包含表达质量字段）";
        row.append(empty);
      } else {
        [...tags].forEach((tag) => {
          const pill = document.createElement("span");
          pill.className = "term forbidden";
          pill.textContent = qualityTagLabel(tag);
          row.append(pill);
        });
      }
      block.append(row);
      container.append(block);
    }
    function moveSelectedCase(offset) {
      const items = visibleCases();
      const index = items.findIndex((item) => item.caseId === state.selectedCaseId);
      const target = items[index + offset];
      if (target) selectCase(target);
    }
    function focusNextReviewCase() {
      const items = state.cases.filter((item) => statusMatches(item, "needs_review") && (!state.roleFilter || item.npcId === state.roleFilter) && caseMatchesSearch(item));
      if (!items.length) { showToast("当前没有符合条件的待复核案例"); return; }
      const index = items.findIndex((item) => item.caseId === state.selectedCaseId);
      selectCase(items[(index + 1) % items.length]);
    }
    function renderCaseNavigation(container, item) {
      const toolbar = document.createElement("div");
      toolbar.className = "case-detail-toolbar";
      toolbar.setAttribute("aria-label", "案例定位");
      const items = visibleCases();
      const index = items.findIndex((candidate) => candidate.caseId === item.caseId);
      const reviewCount = state.cases.filter((candidate) => statusMatches(candidate, "needs_review")).length;
      toolbar.innerHTML = `<span class="case-position">${index >= 0 ? `${index + 1} / ${items.length}` : "当前案例"}</span><div class="case-nav-actions"><button class="case-nav-btn" type="button" data-case-nav="previous" aria-label="上一个测试例">‹ 上一个</button><button class="case-nav-btn" type="button" data-case-nav="next" aria-label="下一个测试例">下一个 ›</button><button class="case-nav-btn review" type="button" data-case-nav="review">下一条待复核 · ${reviewCount}</button></div>`;
      const previous = toolbar.querySelector('[data-case-nav="previous"]');
      const next = toolbar.querySelector('[data-case-nav="next"]');
      if (previous) { previous.disabled = index <= 0; previous.addEventListener("click", () => moveSelectedCase(-1)); }
      if (next) { next.disabled = index < 0 || index >= items.length - 1; next.addEventListener("click", () => moveSelectedCase(1)); }
      toolbar.querySelector('[data-case-nav="review"]')?.addEventListener("click", focusNextReviewCase);
      container.prepend(toolbar);
    }
    function makeDetailSectionsCollapsible(container) {
      const collapsibleTitles = new Set(["期望出现的当前话题证据（用于自动评测提示）", "禁止提前引入或机械化的表达", "表达变化提示", "预置上下文"]);
      container.querySelectorAll(".detail-block").forEach((section) => {
        if (section.dataset.collapsible === "true") return;
        const heading = section.querySelector("h3");
        if (!heading || !collapsibleTitles.has(heading.textContent.trim())) return;
        const content = document.createElement("div");
        content.className = "detail-section-content";
        [...section.children].filter((child) => child !== heading).forEach((child) => content.append(child));
        section.append(content);
        section.dataset.collapsible = "true";
        heading.classList.add("detail-block-heading");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "detail-section-toggle";
        toggle.setAttribute("aria-expanded", "false");
        const updateToggle = () => { toggle.textContent = content.hidden ? "展开" : "收起"; toggle.setAttribute("aria-expanded", String(!content.hidden)); };
        content.hidden = true;
        toggle.addEventListener("click", () => { content.hidden = !content.hidden; updateToggle(); });
        heading.append(toggle);
        updateToggle();
      });
    }
    const baseRenderCaseDetail = renderCaseDetail;
    renderCaseDetail = function () {
      baseRenderCaseDetail();
      const item = state.cases.find((candidate) => candidate.caseId === state.selectedCaseId) || state.cases[0];
      if (!item) return;
      const container = $("case-detail");
      renderCaseNavigation(container, item);
      const strip = container.querySelector(".context-strip");
      if (strip) {
        const stage = document.createElement("span");
        stage.className = `context-chip${highAffinityStages.has(item.relationshipStage) ? " high-affinity" : ""}`;
        stage.innerHTML = `<b>好感</b>${item.gameState?.friendshipHearts ?? 0} 心`;
        strip.append(stage);
      }
      renderStyleQualitySummary(container, item);
      makeDetailSectionsCollapsible(container);
    };
    const baseSelectCase = selectCase;
    selectCase = function (item, openChat = false) {
      if (!item) return;
      baseSelectCase(item, openChat);
      updateCaseViewUrl();
    };
    const baseApplyCaseFilter = applyCaseFilter;
    applyCaseFilter = function (filter) {
      state.filter = caseFilterValues.has(filter) ? filter : "all";
      if (state.filter === "needs_review") state.statusFilter = "needs_review";
      else if (state.statusFilter === "needs_review") state.statusFilter = "";
      baseApplyCaseFilter(state.filter);
      syncCaseFilterControls();
      updateCaseViewUrl();
    };
    function rerenderCaseBrowser() {
      renderFilterCounts();
      renderCaseList();
      selectFirstVisibleCaseIfNeeded();
      renderCaseDetail();
      syncCaseFilterControls();
      updateCaseViewUrl();
    }
    const baseLoadQualityCases = loadQualityCases;
    loadQualityCases = async function () {
      await baseLoadQualityCases();
      populateCaseRoleFilter();
      rerenderCaseBrowser();
    };
    $("case-search")?.addEventListener("input", (event) => {
      state.query = event.target.value.trim();
      rerenderCaseBrowser();
    });
    $("case-search-clear")?.addEventListener("click", () => {
      state.query = "";
      rerenderCaseBrowser();
      $("case-search")?.focus();
    });
    $("case-role-filter")?.addEventListener("change", (event) => {
      state.roleFilter = event.target.value;
      rerenderCaseBrowser();
    });
    $("case-status-filter")?.addEventListener("change", (event) => {
      state.statusFilter = event.target.value;
      if (state.statusFilter === "needs_review") state.filter = "all";
      rerenderCaseBrowser();
    });
    '''
    marker = "    loadQualityCases(); loadHealth();"
    if marker not in script:
        raise ValueError("案例脚本缺少初始化标记")
    script = script.replace(
        'if (state.cases[0]) window.setTimeout(() => selectCase(state.cases[0]), 0);',
        'if (state.cases[0]) window.setTimeout(() => selectCase(initialCaseForSelection()), 0);',
        1,
    )
    return script.replace(marker, enhancement + "\n" + marker, 1)


def _build_integrated_dialogue_lab_template() -> str:
    """把现有三页业务内容装入一个可切换的 Dialogue Lab 工作台。"""

    case_inner = _extract_main_inner(_DIALOGUE_CASE_BROWSER_SOURCE_HTML).replace(
        'href="/test/chat"',
        'href="/test/chat" data-view-target="chat"',
    )
    case_inner = re.sub(
        r'<div class="heading">.*?(?=<div class="browser-layout">)',
        "",
        case_inner,
        count=1,
        flags=re.DOTALL,
    )
    case_inner = re.sub(
        r'<div class="filter-list">.*?</div>',
        (
            '<div class="filter-list">'
            '<button class="filter-btn active" data-filter="all">全部测试例 <span id="filter-all-count">—</span></button>'
            '<button class="filter-btn" data-filter="daily">日常状态 <span id="filter-daily-count">—</span></button>'
            '<button class="filter-btn" data-filter="channel">远程 / 当面 <span id="filter-channel-count">—</span></button>'
            '<button class="filter-btn" data-filter="continuity">上下文续聊 <span id="filter-continuity-count">—</span></button>'
            '<button class="filter-btn review-filter" data-filter="needs_review">待人工复核 <span id="filter-needs-review-count">—</span></button>'
            '<button class="filter-btn" data-filter="high_affinity">高好感 <span id="filter-high-affinity-count">—</span></button>'
            '<button class="filter-btn" data-filter="stranger">初识 <span id="filter-stranger-count">—</span></button>'
            '<button class="filter-btn" data-filter="acquaintance">熟悉 <span id="filter-acquaintance-count">—</span></button>'
            '<button class="filter-btn" data-filter="friend">朋友 <span id="filter-friend-count">—</span></button>'
            '<button class="filter-btn" data-filter="close">亲近 <span id="filter-close-count">—</span></button>'
            '<button class="filter-btn" data-filter="dating">恋爱 <span id="filter-dating-count">—</span></button>'
            '<button class="filter-btn" data-filter="married">婚后 <span id="filter-married-count">—</span></button>'
            '<button class="filter-btn" data-filter="parent">育儿 <span id="filter-parent-count">—</span></button>'
            '</div>'
        ),
        case_inner,
        count=1,
        flags=re.DOTALL,
    )
    case_inner = case_inner.replace(
        '<span id="batch-run-status" class="batch-run-status"></span></div><div class="nav-section">',
        '<span id="batch-run-status" class="batch-run-status"></span></div>'
        '<div class="case-tools" aria-label="测试例快速筛选">'
        '<div class="case-search-row"><label class="case-search-label" for="case-search">搜索测试例</label>'
        '<div class="case-search-input"><input id="case-search" type="search" placeholder="角色、话题、地点或案例 ID" autocomplete="off">'
        '<button class="case-search-clear" id="case-search-clear" type="button" aria-label="清除搜索">清除</button></div></div>'
        '<div class="case-filter-grid">'
        '<label for="case-role-filter">角色<select id="case-role-filter"><option value="">全部角色</option></select></label>'
        '<label for="case-status-filter">结果<select id="case-status-filter">'
        '<option value="">全部结果</option><option value="needs_review">待人工复核</option>'
        '<option value="unrun">未生成</option><option value="passed">自动通过</option><option value="error">生成失败</option>'
        '</select></label></div></div><div class="nav-section">',
        1,
    )
    case_inner = case_inner.replace(
        '<div class="metric"><span>预置上下文</span><strong id="coverage-history">—</strong></div>',
        '<div class="metric"><span>预置上下文</span><strong id="coverage-history">—</strong></div>'
        '<div class="metric"><span>高好感案例</span><strong id="coverage-high-affinity">—</strong></div>',
        1,
    )
    chat_inner = _extract_main_inner(_DIALOGUE_LAB_SOURCE_HTML)
    raw_inner = _extract_main_inner(_RAW_DIALOGUE_REFERENCE_SOURCE_HTML)
    raw_inner = raw_inner.replace('id="npc-select"', 'id="raw-npc-select"')
    raw_inner = raw_inner.replace('id="npc-buttons"', 'id="raw-npc-buttons"')

    case_script = _augment_case_browser_script(
        _extract_script(_DIALOGUE_CASE_BROWSER_SOURCE_HTML)
    )
    chat_script = _extract_script(_DIALOGUE_LAB_SOURCE_HTML)
    raw_script = _extract_script(_RAW_DIALOGUE_REFERENCE_SOURCE_HTML)
    raw_script = raw_script.replace('$("npc-select")', '$("raw-npc-select")')
    raw_script = raw_script.replace('$("npc-buttons")', '$("raw-npc-buttons")')

    integrated_chat_styles = re.sub(
        r"\s*@media\s*\(min-width:1051px\)\s*and\s*\(max-height:900px\)\s*"
        r"\{\s*body\s*\{\s*zoom\s*:\s*\.76;\s*\}\s*\.app\s*\{\s*"
        r"height\s*:\s*calc\(100vh\s*/\s*\.76\);\s*\}\s*\}",
        "",
        _extract_style(_DIALOGUE_LAB_SOURCE_HTML),
        count=1,
    )
    styles = "\n".join(
        (
            _extract_style(_DIALOGUE_CASE_BROWSER_SOURCE_HTML),
            integrated_chat_styles,
            _extract_style(_RAW_DIALOGUE_REFERENCE_SOURCE_HTML),
            DIALOGUE_LAB_SHARED_UI_CSS,
        )
    )
    integrated_styles = """
    #dialogue-lab-workspace.dialogue-lab-shell {
      height:100vh; max-width:1560px; margin:0 auto; padding:14px 18px;
      display:flex; flex-direction:column;
    }
    #dialogue-lab-workspace .workspace-contextbar {
      display:grid; grid-template-columns:minmax(175px,.7fr) minmax(0,1.8fr) minmax(180px,1fr);
      align-items:center; gap:12px; flex:0 0 auto; margin-bottom:10px; padding:9px 12px;
      border:1px solid #cbdaca; border-radius:11px; color:var(--ink); background:#f8fbf6;
      box-shadow:0 5px 16px #3d5d460b;
    }
    #dialogue-lab-workspace .context-identity { min-width:0; }
    #dialogue-lab-workspace .context-eyebrow { display:block; color:var(--muted); font-size:9px; letter-spacing:.1em; text-transform:uppercase; }
    #dialogue-lab-workspace .context-identity strong { display:block; margin-top:2px; color:#315b42; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    #dialogue-lab-workspace .context-pills { display:flex; flex-wrap:wrap; gap:5px; min-width:0; }
    #dialogue-lab-workspace .context-pill { padding:5px 7px; border:1px solid #d8e4d6; border-radius:6px; color:#5c6e61; background:#fff; font-size:10px; white-space:nowrap; }
    #dialogue-lab-workspace .context-pill strong { margin-right:3px; color:#849287; font-weight:500; }
    #dialogue-lab-workspace .context-story { min-width:0; padding-left:10px; border-left:1px solid #d8e4d6; color:#6d786d; font-size:10px; line-height:1.4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    #dialogue-lab-workspace .workspace-content {
      display:flex; flex:1; min-height:0; overflow:hidden; position:relative;
      padding:2px; border:1px solid #d7e1d6; border-radius:15px;
      background:#f0f5ef; box-shadow:0 12px 30px #3d5d4610;
    }
    #dialogue-lab-workspace .workspace-view { display:none; min-height:0; height:100%; width:100%; padding:13px; }
    #dialogue-lab-workspace .workspace-view.is-active { display:flex; flex-direction:column; }
    #dialogue-lab-workspace .workspace-view > .heading,
    #dialogue-lab-workspace .workspace-view > .workspace-view-heading { margin:0 0 11px; }
    #dialogue-lab-workspace .workspace-view .heading h1,
    #dialogue-lab-workspace .workspace-view .workspace-view-heading h1 { color:#304b38; }
    #dialogue-lab-workspace .workspace-view .heading p,
    #dialogue-lab-workspace .workspace-view .workspace-view-heading p { color:var(--muted); }
    #dialogue-lab-workspace .workspace-view .heading-actions .btn,
    #dialogue-lab-workspace .workspace-view .heading-actions .secondary-link { border-color:var(--line); color:var(--ink); background:#ffffffd9; }
    #dialogue-lab-workspace .workspace-view .heading-actions .btn:hover,
    #dialogue-lab-workspace .workspace-view .heading-actions .secondary-link:hover { border-color:#9cbaa4; background:#fff; }
    #dialogue-lab-workspace .workspace-view > .panel,
    #dialogue-lab-workspace .workspace-view > .layout,
    #dialogue-lab-workspace .workspace-view > .browser-layout,
    #dialogue-lab-workspace .workspace-view > .reference-grid { min-width:0; }
    #dialogue-lab-workspace .workspace-view > .layout,
    #dialogue-lab-workspace .workspace-view > .browser-layout { flex:1; min-height:0; }
    #dialogue-lab-workspace [data-workspace-view="raw"] { overflow:auto; padding-bottom:3px; }
    #dialogue-lab-workspace [data-workspace-view="raw"] > .toolbar { flex:0 0 auto; }
    #dialogue-lab-workspace [data-workspace-view="raw"] > .reference-grid { flex:1; min-height:0; grid-template-rows:minmax(0,1fr); margin-top:12px; }
    #dialogue-lab-workspace [data-workspace-view="raw"] > .reference-grid > .reference-section { min-height:0; display:flex; flex-direction:column; overflow:hidden; }
    #dialogue-lab-workspace [data-workspace-view="raw"] .raw-dialogue-list { flex:1; min-height:0; max-height:none; overflow-y:auto; overflow-x:hidden; }
    .workspace-view-heading { display:flex; align-items:end; justify-content:space-between; gap:12px; flex:0 0 auto; margin:0 2px 11px; }
    .workspace-view-heading h1 { margin:0; font-size:22px; letter-spacing:-.03em; }
    .workspace-view-heading p { margin:4px 0 0; color:var(--muted); font-size:12px; }
    .workspace-view-heading .heading-actions { display:flex; flex-wrap:wrap; gap:7px; }
    .workspace-view-heading .secondary-link { display:inline-flex; align-items:center; padding:7px 10px; border:1px solid var(--line); border-radius:8px; color:var(--ink); background:#ffffffc9; text-decoration:none; font-size:11px; }
    .workspace-view-heading .secondary-link:hover { border-color:#9cbaa4; background:#fff; }
    #dialogue-lab-workspace .workspace-view .panel-header,
    #dialogue-lab-workspace .workspace-view .section-heading { border-color:var(--line); background:#fafcf8; }
    #dialogue-lab-workspace .workspace-view .btn,
    #dialogue-lab-workspace .workspace-view button.secondary,
    #dialogue-lab-workspace .workspace-view .back-link { border-color:var(--line); border-radius:8px; color:var(--ink); background:#fff; }
    #dialogue-lab-workspace .workspace-view .btn:hover,
    #dialogue-lab-workspace .workspace-view button.secondary:hover,
    #dialogue-lab-workspace .workspace-view .back-link:hover { border-color:#9cbaa4; color:var(--accent-dark); background:var(--accent-soft); }
    #dialogue-lab-workspace .workspace-view .btn.gold { border-color:#d6b273; color:#795821; background:var(--gold-soft); }
    #dialogue-lab-workspace .workspace-view .case-row,
    #dialogue-lab-workspace .workspace-view .filter-btn { border-color:transparent; background:#fff; }
    #dialogue-lab-workspace .workspace-view .case-row.active,
    #dialogue-lab-workspace .workspace-view .filter-btn.active { border-color:#98b99f; color:var(--green); background:var(--green-soft); }
    @media (max-width:1050px) {
      #dialogue-lab-workspace.dialogue-lab-shell { height:auto; min-height:100vh; }
      #dialogue-lab-workspace .workspace-content { overflow:visible; }
      #dialogue-lab-workspace .workspace-view { height:auto; min-height:0; }
      #dialogue-lab-workspace .workspace-view.is-active { overflow:visible; }
      #dialogue-lab-workspace [data-workspace-view="cases"] .browser-layout,
      #dialogue-lab-workspace [data-workspace-view="chat"] .layout,
      #dialogue-lab-workspace [data-workspace-view="raw"] .reference-grid { grid-template-columns:1fr; min-height:0; }
      #dialogue-lab-workspace [data-workspace-view="chat"] .transcript-panel { min-height:60vh; }
    }
    @media (max-width:700px) {
      #dialogue-lab-workspace.dialogue-lab-shell { padding:8px; }
      #dialogue-lab-workspace .workspace-content { padding:0; border:0; background:transparent; box-shadow:none; }
      #dialogue-lab-workspace .workspace-view { padding:0; }
      .workspace-view-heading { align-items:start; flex-direction:column; gap:7px; }
      .workspace-view-heading .heading-actions { width:100%; }
      #dialogue-lab-workspace [data-workspace-view="chat"] .layout,
      #dialogue-lab-workspace [data-workspace-view="cases"] .browser-layout,
      #dialogue-lab-workspace [data-workspace-view="raw"] .reference-grid { grid-template-columns:1fr; }
      #dialogue-lab-workspace .workspace-contextbar { grid-template-columns:1fr; gap:6px; padding:8px 9px; }
      #dialogue-lab-workspace .context-story { padding:0; border:0; white-space:normal; }
      #dialogue-lab-workspace [data-workspace-view="cases"] .case-detail-toolbar { top:-1px; margin:-1px -9px 9px; padding:7px 9px; }
      #dialogue-lab-workspace [data-workspace-view="cases"] .case-nav-actions { justify-content:flex-start; }
    }
    """

    nav = """
      <nav class="workspace-nav" aria-label="工作台导航">
        <a class="workspace-tab" href="/test" data-view-target="cases" __CASES_CURRENT__>测试例浏览</a>
        <a class="workspace-tab" href="/test/chat" data-view-target="chat" __CHAT_CURRENT__>单次聊天</a>
        <a class="workspace-tab" href="/raw" data-view-target="raw" __RAW_CURRENT__>原始对白</a>
      </nav>
    """
    chat_heading = """
      <div class="workspace-view-heading">
        <div><h1>单次聊天</h1><p>在指定关系、时间、地点和聊天渠道下验证一轮连续对话。</p></div>
        <div class="heading-actions">
          <a class="secondary-link" href="/raw" data-view-target="raw">查看原始对白</a>
          <button class="secondary" id="clear-session" type="button">清空会话</button>
          <button class="secondary" id="export-session" type="button">导出 JSON</button>
        </div>
      </div>
    """
    case_heading = """
      <div class="workspace-view-heading">
        <div><h1>测试例浏览</h1><p>按角色和场景查看固定评测定义，再进入聊天验证具体回复。</p></div>
        <div class="heading-actions">
          <a class="secondary-link" href="/test/chat" data-view-target="chat">打开单次聊天</a>
          <button class="secondary" id="export-case" type="button">导出当前例</button>
        </div>
      </div>
    """
    raw_heading = """
      <div class="workspace-view-heading">
        <div><h1>原始对白参照</h1><p>查看已解析原文，作为角色语气和事实边界的人工参照。</p></div>
        <div class="heading-actions"><a class="secondary-link" href="/test" data-view-target="cases">回到测试例</a></div>
      </div>
    """

    return (
        "<!doctype html>\n"
        "<html lang=\"zh-CN\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "  <title>Stardew AI NPC · Dialogue Lab</title>\n"
        "  <style>\n"
        + styles
        + integrated_styles
        + "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main id=\"dialogue-lab-workspace\" class=\"dialogue-lab-shell\" data-ui-shell=\"v4\" data-default-view=\"__DEFAULT_VIEW__\">\n"
        "    <header class=\"workspace-topbar topbar\">\n"
        "      <div class=\"workspace-brand brand\"><div class=\"workspace-mark mark\">✦</div><div><div class=\"workspace-eyebrow eyebrow\">Stardew AI NPC · Dialogue Lab</div><strong>角色对话评测工作台</strong><div class=\"workspace-subtitle\">案例、聊天、原文参照集中在一个工作区</div></div></div>\n"
        + nav
        + "      <div class=\"top-meta\"><span class=\"prototype\">本地评测工作台</span><span id=\"health\" class=\"health\">Bridge 检查中……</span></div>\n"
        "    </header>\n"
        "    <section class=\"workspace-contextbar\" aria-live=\"polite\" aria-label=\"当前评测上下文\">\n"
        "      <div class=\"context-identity\"><span class=\"context-eyebrow\">当前评测上下文</span><strong id=\"context-character\">Rasmodia / Wizard</strong></div>\n"
        "      <div class=\"context-pills\"><span class=\"context-pill\"><strong>案例</strong><span id=\"context-case\">尚未选择</span></span><span class=\"context-pill\"><strong>关系</strong><span id=\"context-stage\">—</span></span><span class=\"context-pill\"><strong>渠道</strong><span id=\"context-channel\">—</span></span><span class=\"context-pill\"><strong>场景</strong><span id=\"context-scene\">—</span></span></div>\n"
        "      <div class=\"context-story\" id=\"context-story\">从测试例或原文参照选择一个角色，三项视图会共享这组上下文。</div>\n"
        "    </section>\n"
        "    <div class=\"workspace-content\">\n"
        "    <section id=\"test-case-browser\" class=\"workspace-view __CASES_CLASS__\" data-workspace-view=\"cases\">\n"
        + case_heading
        + case_inner
        + "    </section>\n"
        "    <section id=\"dialogue-chat-view\" class=\"workspace-view __CHAT_CLASS__\" data-workspace-view=\"chat\">\n"
        + chat_heading
        + chat_inner
        + "    </section>\n"
        "    <section id=\"raw-dialogue-page\" class=\"workspace-view __RAW_CLASS__\" data-workspace-view=\"raw\">\n"
        + raw_heading
        + raw_inner
        + "    </section>\n"
        + "    </div>\n"
        + "    "
        + _extract_case_toast(_DIALOGUE_CASE_BROWSER_SOURCE_HTML)
        + "  </main>\n"
        "  <script>\n(function () {\n"
        + case_script
        + "\n})();\n</script>\n"
        "  <script>\n(function () {\n"
        + chat_script
        + "\n})();\n</script>\n"
        "  <script>\n(function () {\n"
        + raw_script
        + "\n})();\n</script>\n"
        "  <script>\n"
        "    (function () {\n"
        "      const root = document.getElementById(\"dialogue-lab-workspace\");\n"
        "      const sharedSelection = window.__dialogueLabSelection = window.__dialogueLabSelection || { npcId: \"Wizard\", caseItem: null };\n"
        "      const views = [...root.querySelectorAll(\"[data-workspace-view]\")];\n"
        "      const navTabs = [...root.querySelectorAll(\".workspace-tab\")];\n"
        "      const viewLinks = [...root.querySelectorAll(\"[data-view-target]\")];\n"
        "      const validViews = new Set(views.map((view) => view.dataset.workspaceView));\n"
        "      function viewFromLocation() {\n"
        "        const queryView = new URLSearchParams(window.location.search).get(\"view\");\n"
        "        const hashView = window.location.hash.replace(\"#\", \"\");\n"
        "        const candidate = queryView || hashView || root.dataset.defaultView;\n"
        "        return validViews.has(candidate) ? candidate : root.dataset.defaultView;\n"
        "      }\n"
        "      function updateSharedContext(detail) {\n"
        "        const item = detail && typeof detail === \"object\" ? detail : {};\n"
        "        const npcId = item.npcId || sharedSelection.npcId || \"Wizard\";\n"
        "        const displayName = item.displayName || ({Wizard: \"Rasmodia / Wizard\", Sophia: \"Sophia\", Shane: \"Shane\", Sebastian: \"Sebastian\", Alex: \"Alex\"}[npcId] || npcId);\n"
        "        const gameState = item.gameState || {};\n"
        "        const scene = [gameState.season, gameState.date, gameState.weather, gameState.time, gameState.location].filter((value) => value !== undefined && value !== null && value !== \"\").join(\" · \") || \"未设置\";\n"
        "        root.querySelector(\"#context-character\").textContent = displayName;\n"
        "        root.querySelector(\"#context-case\").textContent = item.caseId || sharedSelection.caseItem?.caseId || \"角色参照\";\n"
        "        root.querySelector(\"#context-stage\").textContent = item.relationshipStage || \"—\";\n"
        "        root.querySelector(\"#context-channel\").textContent = item.channel === \"remote\" ? \"远程\" : item.channel === \"face_to_face\" ? \"当面\" : \"—\";\n"
        "        root.querySelector(\"#context-scene\").textContent = scene;\n"
        "        root.querySelector(\"#context-story\").textContent = item.storyProgress || \"已同步角色；从测试例进入聊天时会一并带入场景、渠道和预置上下文。\";\n"
        "      }\n"
        "      function selectNpc(npcId) {\n"
        "        const canonicalId = npcId === \"Rasmodia\" ? \"Wizard\" : npcId || \"Wizard\";\n"
        "        sharedSelection.npcId = canonicalId;\n"
        "        sharedSelection.caseItem = null;\n"
        "        window.dispatchEvent(new CustomEvent(\"dialogue-lab:npc-selected\", { detail: { npcId: canonicalId } }));\n"
        "        updateSharedContext({ npcId: canonicalId });\n"
        "      }\n"
        "      function selectCase(item, openChat = false) {\n"
        "        if (!item) return;\n"
        "        sharedSelection.caseItem = item;\n"
        "        sharedSelection.npcId = item.npcId || \"Wizard\";\n"
        "        window.dispatchEvent(new CustomEvent(\"dialogue-lab:case-selected\", { detail: item }));\n"
        "        updateSharedContext(item);\n"
        "        if (openChat) showWorkspaceView(\"chat\");\n"
        "      }\n"
        "      function showWorkspaceView(view, updateUrl = true) {\n"
        "        const selected = validViews.has(view) ? view : root.dataset.defaultView;\n"
        "        views.forEach((element) => { const active = element.dataset.workspaceView === selected; element.classList.toggle(\"is-active\", active); });\n"
        "        navTabs.forEach((tab) => { const active = tab.dataset.viewTarget === selected; tab.classList.toggle(\"active\", active); if (active) tab.setAttribute(\"aria-current\", \"page\"); else tab.removeAttribute(\"aria-current\"); });\n"
        "        if (updateUrl) { const url = new URL(window.location.href); url.pathname = \"/test\"; url.searchParams.set(\"view\", selected); url.hash = \"\"; window.history.replaceState({}, \"\", url); }\n"
        "      }\n"
        "      window.DialogueLab = { selectNpc, selectCase, showView: showWorkspaceView };\n"
        "      window.addEventListener(\"dialogue-lab:case-selected\", (event) => { sharedSelection.caseItem = event.detail || null; sharedSelection.npcId = event.detail?.npcId || sharedSelection.npcId; updateSharedContext(event.detail); window.dispatchEvent(new CustomEvent(\"dialogue-lab:apply-case\", { detail: event.detail })); });\n"
        "      window.addEventListener(\"dialogue-lab:npc-selected\", (event) => { sharedSelection.npcId = event.detail?.npcId || sharedSelection.npcId; sharedSelection.caseItem = null; updateSharedContext(event.detail); });\n"
        "      viewLinks.forEach((link) => link.addEventListener(\"click\", (event) => { event.preventDefault(); showWorkspaceView(link.dataset.viewTarget); }));\n"
        "      window.addEventListener(\"popstate\", () => showWorkspaceView(viewFromLocation(), false));\n"
        "      showWorkspaceView(viewFromLocation(), false);\n"
        "      updateSharedContext(sharedSelection.caseItem || { npcId: sharedSelection.npcId });\n"
        "    })();\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


_INTEGRATED_DIALOGUE_LAB_TEMPLATE = _build_integrated_dialogue_lab_template()


def integrated_dialogue_lab_page(default_view: str = "cases") -> str:
    """返回单页工作台；旧路由只决定首次打开的视图。"""

    view = default_view if default_view in {"cases", "chat", "raw"} else "cases"
    html = _INTEGRATED_DIALOGUE_LAB_TEMPLATE.replace("__DEFAULT_VIEW__", view)
    for name in ("cases", "chat", "raw"):
        html = html.replace(
            f"__{name.upper()}_CLASS__",
            "is-active" if name == view else "",
        )
        html = html.replace(
            f"__{name.upper()}_CURRENT__",
            'aria-current="page"' if name == view else "",
        )
    return html
