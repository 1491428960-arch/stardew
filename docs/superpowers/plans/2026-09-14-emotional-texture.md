# 角色专属情绪纹理实现计划

> 目标：让 deep-flirt 覆盖的角色在当前话题触发时表现一个短暂、角色化的局部反应，同时保留现有关系、同意和质量 Guard 边界。

## 约束

- 只修改当前 `story-memory` 工作树，保留所有已有未提交修改。
- 不发起 DeepSeek/Gemini 或其他云端请求，不启动游戏、SMAPI、Bridge 服务。
- 不修改 Guard 判定、采样参数、历史结果工件或字符串后处理。
- 普通套件和没有 `emotionTexture` 的角色保持旧 Prompt 契约。

## 实现步骤

1. **角色资料补充专属纹理**
   - 文件：`data/personas/female-bachelors.json`、`data/personas/sve.json`、`data/personas/rasmodia.json`。
   - 为 Shane、Sebastian、Sophia、Harvey、Sam、Alex、Elliott、Wizard 写入各自不同的 `voiceStyle.emotionTexture`。
   - 每条纹理只描述触发条件和可见表达动作，不要求模型说出情绪标签，也不引入全局随机状态。

2. **Prompt 压缩与自然契约**
   - 文件：`bridge/src/stardew_ai_bridge/prompts.py`。
   - 让 `_compact_voice_style()` 在存在时保留短的 `emotionTexture` 字段，普通角色缺失该字段时不注入空值。
   - 在 `natural_dialogue_contract` 中增加：每轮最多一个微反应；可用停顿、改口、短暂回避、玩笑后认真或突然变短表达；不要直接说出情绪标签；不要为展示纹理凭空制造冲突。
   - 不改变默认模式的 `mustMention`、conversation lead、关系卡或 Guard 逻辑。

3. **测试与验证**
   - 先运行已新增的情绪纹理回归，确认生产代码修改前的 3 个红灯已变绿。
   - 定向运行：
     `bridge/tests/test_prompts.py bridge/tests/test_character_quality_eval.py` 中情绪纹理与自然契约相关测试。
   - 再运行 Bridge 全量 Python 测试：
     `py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests`
   - 运行 `py -3.10 -B -m compileall -q bridge/src scripts` 与 `git diff --check`。
   - 最后检查 `git status --short --branch`，确认只新增本计划、角色纹理和 Prompt/测试相关改动，其他既有修改仍在。

## 预期结果

- 8 个 deep-flirt 角色各自的纹理会进入自然模式 Prompt，并且彼此可区分。
- 自然模式允许局部情绪起伏，但不会把情绪名词变成台词任务，也不会因缺少起伏触发重试。
- 无纹理普通角色的既有 Prompt 输出不变。
- 所有验证均为离线证据；真实 DeepSeek 自然度留待后续由用户决定的小批量 A/B。
