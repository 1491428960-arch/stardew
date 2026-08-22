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
