# Refactor Dev Status

## 已完成范围

按 `refactor_guide.md` 完成阶段 1、2、3、4、5、6、7 的主要重构。

## 关键改动

- 修复 `SecondClass` 数据库行转换：`place_info -> placeInfo`、`participation_form -> form`。
- 修复活动列表地点展示逻辑，有地点时显示真实地点，无地点时显示“未提供”。
- `SecondClassDB` 快照写入改为 `executemany`。
- 用户偏好写入改为单事务互斥，新增 `PreferenceRepository` 和轻量 `meta(schema_version)`。
- 新增 `ActivityRepository`，集中活动快照只读查询。
- 新增服务层：
  - `ActivityQueryService`
  - `ActivityUpdateService`
  - `EnrollmentService`
- `/valid`、`/search`、`/info` 查询改为走查询服务。
- `/valid 深度`、`/search` 深度刷新、卡片查看子活动改为走深度更新服务。
- `/join`、`/cancel`、卡片报名/取消报名改为走报名服务。
- `SecondClassBatchUpdater` 的 `continue_on_error=False` 改为真实 fail-fast。
- 新增标准库 `unittest` 回归测试：`tests/test_refactor_stage_1_2.py`。
- 新增 `ActivityFilterPipeline`，统一 scanner 新活动通知和 `/valid` 的筛选流程。
- 明确感兴趣白名单语义：不绕过状态和已报名等硬约束，但绕过忽略、重叠、时间、AI 等用户侧筛选。
- `ignore_overlap` 改为通过构造参数和 `FilterContext` 显式传入，筛选管线不再读取全局 settings。
- 新增 `src/context/`，用单实例 `ContextManager` 管理搜索结果、最近展示活动、确认操作和过期策略。
- `UserSession` 收敛为飞书身份字段与 `ContextManager` 入口，不再承载业务上下文。
- `/search`、`/valid`、`/info`、通知监听器、报名/取消/升级确认流程改为读写 `ContextManager`。
- `/interested` 支持恢复 `overlay/重叠` 类型的筛选结果。
- 新增阶段 4/5 回归测试：`tests/test_refactor_stage_4_5.py`。
- 新增 `src/core/scanning/`，将扫描同步、diff、事件发布和版本调度从 `ActivityScanner` 中拆出。
- `ActivityScanner` 收敛为定时任务生命周期和旧 `scan(...)` 兼容入口。
- `EventBus.publish()` 返回 `EventPublishResult`，可聚合 listener 执行失败。
- 新活动通知支持 `wait_for_notifications=True` 时把通知失败写入 `ScanResult.notification_errors`。
- `NotificationListener` 改为通过构造参数接收通知展示配置，发送失败会抛出可聚合异常。
- 新增 `src/app/` 与 `AppContext`，集中应用运行时依赖。
- `MessageRouter` 和指令 Handler 改为实例级 `AppContext` 注入，移除 Handler 类变量依赖入口。
- `CardActionHandler` 改为构造函数注入应用上下文和 bot getter，不再二次 `set_dependencies`。
- `NotificationService`、卡片子活动发送和日历同步不再主动读取全局 `get_settings()`。
- 新增阶段 6/7 回归测试：`tests/test_refactor_stage_6_7.py`。

## 验证

- `/home/amsors/anaconda3/envs/pyustc/bin/python -m compileall src tests` 通过。
- `/home/amsors/anaconda3/envs/pyustc/bin/python -m unittest discover -s tests -v` 通过，13 个测试全绿。
- `git diff --check` 通过。

## 注意

- 沙箱内运行 `aiosqlite` 相关测试会卡住，最终单测是在沙箱外执行通过的。
- 未手动触发真实 USTC/飞书链路。
