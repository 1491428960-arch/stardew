from __future__ import annotations


def group_dialogue_lab_page() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>多人对话实验 · Stardew AI NPC</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, "Microsoft YaHei", sans-serif; }
    body { margin: 0; background: #17151b; color: #f6efff; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 6px; font-size: 1.65rem; }
    p { color: #c7bdd1; }
    .toolbar, .results { display: grid; gap: 14px; margin-top: 18px; }
    .toolbar { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    label { display: grid; gap: 6px; color: #d8cade; font-size: .88rem; }
    input, select, textarea, button { border: 1px solid #51435d; border-radius: 8px; padding: 9px 10px; background: #211d27; color: #fff; font: inherit; }
    select[multiple] { min-height: 130px; }
    textarea { min-height: 80px; resize: vertical; }
    .wide { grid-column: 1 / -1; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    button { cursor: pointer; background: #6e4aa1; border-color: #a77bd8; }
    button.secondary { background: #2d2734; }
    button:disabled { cursor: wait; opacity: .55; }
    .hint { color: #a99aae; font-size: .82rem; }
    .review-link { display: inline-flex; align-items: center; gap: 6px; color: #d9c6ff; font-size: .86rem; text-decoration: none; }
    .review-link:hover { color: #fff; text-decoration: underline; }
    .results { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .card { border: 1px solid #51435d; border-radius: 10px; padding: 14px; background: #1e1a24; min-height: 190px; }
    .card h2 { margin: 0 0 8px; font-size: 1.05rem; }
    .metric { color: #c7bdd1; font-size: .8rem; line-height: 1.65; }
    .turn { border-left: 3px solid #a77bd8; margin: 10px 0; padding-left: 10px; line-height: 1.55; }
    .turn strong { color: #f4c7ff; }
    .error { color: #ffafaf; white-space: pre-wrap; }
    @media (max-width: 850px) { .toolbar, .results { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>线上多人对话实验</h1>
  <p>同一组参与者、同一条输入，比较三种多人生成策略。当前固定为 <strong>remote</strong>；Fake 只用于结构演示，不是真实 AI。</p>
  <input id="group-channel" type="hidden" value="remote">
  <section class="toolbar">
    <label>参与 NPC（选择 2～3 人）
      <select id="group-participants" multiple></select>
    </label>
    <label>策略
      <select id="group-strategy">
        <option value="turn_based">轮流单发言人</option>
        <option value="fanout">独立并行回复</option>
        <option value="multi_turn">自然接话流（可插话）</option>
      </select>
    </label>
    <label>最多回合数（自然接话流）
      <select id="group-turn-count">
        <option value="2">2 回合</option>
        <option value="3" selected>3 回合</option>
        <option value="4">4 回合</option>
      </select>
    </label>
    <label>当前发言人
      <select id="active-speaker"></select>
    </label>
    <label>Provider
      <select id="group-provider">
        <option value="fake">Fake（本地演示）</option>
        <option value="cloud">Gemini 云端</option>
        <option value="auto">自动</option>
        <option value="local">Qwen 本地</option>
      </select>
    </label>
    <label class="wide">玩家输入
      <textarea id="group-message">你们最近都在忙什么？</textarea>
    </label>
    <div class="actions wide">
      <button id="send-one" type="button">运行当前策略</button>
      <button id="send-all" class="secondary" type="button">同一输入比较三种策略</button>
      <button id="clear" class="secondary" type="button">清空结果</button>
      <a class="review-link" href="/test/group/review">查看已生成的云端样本 →</a>
    </div>
    <div class="hint wide">自然接话流不会强制每人一句：可以有人先接、有人插话，也可以同一 NPC 连续补一句，最多输出上面选定的回合数；所有对白仍公开，不能添加名单外角色、改变关系或把远程聊天写成线下见面。</div>
  </section>
  <section id="results" class="results" aria-live="polite"></section>
</main>
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const participants = $("group-participants");
  const activeSpeaker = $("active-speaker");
  const results = $("results");
  const state = { catalog: [], history: [] };
  const strategyLabels = { fanout: "独立并行回复", turn_based: "轮流单发言人", multi_turn: "自然接话流（可插话）" };

  function selectedNpcIds() { return [...participants.selectedOptions].map((item) => item.value); }
  function selectedParticipants() {
    const ids = new Set(selectedNpcIds());
    return state.catalog.filter((item) => ids.has(item.npcId)).map((item) => ({ npcId: item.npcId, displayName: item.displayName || item.npcId, sourceMods: item.sourceMods || [] }));
  }
  function syncActiveSpeakers() {
    const selected = selectedNpcIds();
    const old = activeSpeaker.value;
    activeSpeaker.replaceChildren();
    selected.forEach((id) => {
      const option = document.createElement("option"); option.value = id; option.textContent = id; activeSpeaker.append(option);
    });
    activeSpeaker.value = selected.includes(old) ? old : (selected[0] || "");
  }
  function renderResult(strategy, body, error = "") {
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("h2"); title.textContent = strategyLabels[strategy] || strategy; card.append(title);
    const metric = document.createElement("div"); metric.className = "metric";
    const usage = body.usage ? ` · tokens ${body.usage.totalTokens ?? "未返回"}` : " · tokens 未返回";
    metric.textContent = `provider=${body.provider || "unknown"} · calls=${body.providerCalls ?? 0} · fallback=${body.fallbackCount ?? 0} · latency=${body.latencyMs ?? 0}ms${usage}`; card.append(metric);
    if (error || (body.providerErrors && body.providerErrors.length)) { const box = document.createElement("div"); box.className = "error"; box.textContent = error || body.providerErrors.join("\\n"); card.append(box); }
    (body.turns || []).forEach((turn) => { const line = document.createElement("div"); line.className = "turn"; const speaker = document.createElement("strong"); speaker.textContent = `${turn.speakerNpcId}：`; line.append(speaker, document.createTextNode(turn.content)); card.append(line); });
    results.append(card);
  }
  function buildPayload(strategy) {
    return { message: $("group-message").value.trim(), provider: $("group-provider").value, strategy, channel: "remote", participants: selectedParticipants(), activeSpeakerNpcId: activeSpeaker.value, history: state.history, turnCount: Number($("group-turn-count").value) || 2 };
  }
  async function run(strategy) {
    const payload = buildPayload(strategy);
    if (payload.participants.length < 2 || payload.participants.length > 3) { renderResult(strategy, {}, "请选择 2～3 个参与 NPC。"); return; }
    try {
      const response = await fetch("/api/dialogue/group", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      const body = await response.json();
      if (!response.ok) { renderResult(strategy, body, JSON.stringify(body.detail || body)); return; }
      renderResult(strategy, body);
    } catch (error) { renderResult(strategy, {}, String(error)); }
  }
  async function loadCatalog() {
    const response = await fetch("/api/npcs"); const body = await response.json(); state.catalog = body.npcs || [];
    state.catalog.forEach((item) => { const option = document.createElement("option"); option.value = item.npcId; option.textContent = item.displayName ? `${item.displayName}（${item.npcId}）` : item.npcId; if (["Abigail", "Emily"].includes(item.npcId)) option.selected = true; participants.append(option); });
    syncActiveSpeakers();
  }
  participants.addEventListener("change", syncActiveSpeakers);
  $("send-one").addEventListener("click", async () => { $("send-one").disabled = true; await run($("group-strategy").value); $("send-one").disabled = false; });
  $("send-all").addEventListener("click", async () => { $("send-all").disabled = true; for (const strategy of ["fanout", "turn_based", "multi_turn"]) await run(strategy); $("send-all").disabled = false; });
  $("clear").addEventListener("click", () => results.replaceChildren());
  loadCatalog().catch((error) => renderResult("catalog", {}, `加载 NPC 目录失败：${error}`));
})();
</script>
</body>
</html>"""
