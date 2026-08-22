# Stardew AI NPC

本项目用于探索 Stardew Valley AI NPC 集成方案。Python Bridge 位于
`bridge/`，当前提供可重复安装和测试的独立工程骨架。

## 开发环境

- Python 3.12
- FastAPI
- httpx
- uvicorn
- pytest
- pytest-asyncio

在项目根目录执行以下命令创建虚拟环境并安装开发依赖：

```powershell
Set-Location bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

项目不提交密钥、用户数据、虚拟环境或构建产物。

## Task 8 运行与安全边界

启动 Bridge：

~~~powershell
.\scripts\start_bridge.ps1
~~~

默认监听 http://127.0.0.1:5678；测试页为 /test，健康检查为 /health，对话接口为 POST /api/dialogue/test。Provider 按 local → cloud → fallback 回退；Bridge 关闭、超时或两个 Provider 均失败时，SMAPI 客户端保持 offline/fallback，不阻断游戏。

SMAPI 原型默认按 F8 触发 Rasmodia 对话。安装 Generic Mod Config Menu（GMCM）后，可在游戏内配置 `DialogueKey`、`EnableDialogue`、`BridgeEndpoint` 和 `BridgeTimeoutSeconds`；未安装 GMCM 时配置页会安全跳过。配置仍可直接写入 `config.json`，非法快捷键、非本机回环地址和越界超时会回退到安全默认值。SVE 和娘化 NPC 资料通过 npcId、显示名和来源 mod 兼容，实际是否加载成功需用户在 AI-SVE-测试 profile 内进入游戏确认。回归脚本只读检查 profile、Mods、日志和存档元数据，记录运行前后存档大小/时间戳；默认不启动游戏、不删除或覆盖存档、不修改源 Mods 仓库、不写注册表。实际存档变化、SVE/娘化加载、游戏内对话和日志证据必须由用户亲自操作确认。
