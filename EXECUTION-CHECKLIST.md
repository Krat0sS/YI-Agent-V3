# YI-Framework 执行清单（最终版 2026-05-06）

> 前一个动作不过，绝不开始下一个。

## Action 0：冻结并测绘现有代码 ✅ 已完成
- [x] 画出 conversation.py send() 的真实调用图
- [x] 确认 dayan.py 出卦后的数据流

## Action 1：创建 yi_framework/profiles.py ✅ 已完成
- [x] ExecutionProfile dataclass
- [x] derive_profile(hexagram_name) — 8卦基础属性自动推导64卦
- [x] 单元测试覆盖

## Action 2：在 conversation.py 里切开 LLM 的"神经" ✅ 已完成
- [x] send() 里，dayan 出卦后第一步改为查 derive_profile
- [x] 旧代码（时辰/万物/五行/变爻）用 `if False:` 注释掉，不删
- [x] 验收：日志看到卦名 + ExecutionProfile 值，且不被 LLM 改写

## Action 3：让 ExecutionProfile 真的卡住执行 ✅ 已完成
- [x] 修改 registry.py execute() — 新增 risk_tolerance 参数
- [x] 修改 conversation.py _execute_tool() — 用 profile.timeout_seconds 替代 config.TOOL_TIMEOUT
- [x] 所有 registry.execute 调用点传入 profile.risk_tolerance
- [x] 验收：registry 在 risk_tolerance < tool_risk 时返回 blocked

## Action 4：植入 YiRuntime 并挂载 tick ✅ 已完成（在 Action 2 中一并完成）
- [x] YiRuntime 类已存在于 yi_framework/runtime.py
- [x] tick() 已挂载到 _execute_tool() 每次工具调用后
- [x] 动爻翻转时自动切换 ExecutionProfile
- [ ] 验收（待测试）：连续注入失败，第N次触发动爻，日志输出卦象切换

## Action 5：残忍删除冗余层 ✅ 已完成
- [x] 删除 orchestrator.py (354行)、taiji.py (357行)、change_engine.py (328行)
- [x] 删除 temporal.py (263行)、wanwu.py (347行)
- [x] 清理 conversation.py 所有 `if False:` 块和死代码
- [x] 删除 _HEXAGRAM_ACTION、_TaijiResult、_taiji_diagnose 及辅助方法
- [x] 验收：无残留引用，conversation.py 1248→1016 行（-18.6%），5个文件删除共1649行

## Action 6：工具脆弱性加固和错误注入测试（1周）⬅️ 当前
- [ ] desktop.py 窗口匹配改模糊正则
- [ ] browser.py 处理页面崩溃中间态
- [ ] 所有工具统一异常分类
- [ ] 验收：100次异常模拟，恢复率 > 80%

## Action 7：关闭学习闭环（1周）
- [ ] 接入 gua_tool_effectiveness 表
- [ ] 验收：同一任务第5次耗时 < 第1次的 80%
