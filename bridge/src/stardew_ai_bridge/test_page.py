from __future__ import annotations


TEST_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stardew AI NPC 对话测试页</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f4efe7; color: #31271f; }
    main { max-width: 780px; margin: 32px auto; padding: 24px; }
    section { background: #fffaf2; border: 1px solid #d8c8b4; border-radius: 14px;
      box-shadow: 0 8px 24px #5c453318; padding: 20px; }
    h1 { margin-top: 0; font-size: 1.6rem; }
    .grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    label { display: grid; gap: 5px; font-size: .9rem; }
    .wide { grid-column: 1 / -1; }
    input, select, textarea, button { border: 1px solid #c7b39a; border-radius: 8px;
      box-sizing: border-box; font: inherit; padding: 9px 10px; }
    textarea { min-height: 100px; resize: vertical; }
    button { background: #6d4c36; color: white; cursor: pointer; }
    button:disabled { cursor: wait; opacity: .65; }
    #reply { background: #f0e4d4; min-height: 72px; white-space: pre-wrap; }
    .status { color: #6d4c36; min-height: 1.4em; }
    @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>NPC 对话测试页</h1>
      <p class="status" id="status" aria-live="polite"></p>
      <div class="grid">
        <label>NPC<select id="npc-select"></select></label>
        <label>关系状态<input id="relationship" value="朋友"></label>
        <label>日期<input id="date" value="春 1 日"></label>
        <label>天气<input id="weather" value="晴天"></label>
        <label>地点<input id="location" value="法师塔"></label>
        <label>好感度<input id="friendship" type="number" min="0" value="128"></label>
        <label class="wide">玩家输入<textarea id="message">你好，今天过得怎么样？</textarea></label>
        <button class="wide" id="send" type="button">发送 Fake 对话</button>
      </div>
      <h2>NPC 回复</h2>
      <div id="reply" role="status"></div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const status = $("status");
    const npcSelect = $("npc-select");

    async function loadNpcs() {
      const response = await fetch("/api/npcs");
      if (!response.ok) throw new Error("NPC 资料加载失败");
      const data = await response.json();
      for (const npc of data.npcs) {
        const option = document.createElement("option");
        option.value = npc.npcId;
        option.textContent = `${npc.displayName} (${npc.npcId})`;
        npcSelect.append(option);
      }
    }

    async function sendDialogue() {
      $("send").disabled = true;
      status.textContent = "请求中……";
      const payload = {
        npcId: npcSelect.value,
        message: $("message").value,
        date: $("date").value,
        weather: $("weather").value,
        location: $("location").value,
        friendship: Number($("friendship").value),
        relationship: $("relationship").value,
        provider: "fake"
      };
      try {
        const response = await fetch("/api/dialogue/test", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "对话请求失败");
        $("reply").textContent = data.reply;
        status.textContent = `Provider: ${data.provider} · 延迟: ${data.latencyMs} ms`;
      } catch (error) {
        status.textContent = error.message;
        $("reply").textContent = "";
      } finally {
        $("send").disabled = false;
      }
    }

    $("send").addEventListener("click", sendDialogue);
    loadNpcs().catch((error) => { status.textContent = error.message; });
  </script>
</body>
</html>
"""
