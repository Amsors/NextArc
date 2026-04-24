# Refactor Dev Status

## 已完成范围

按 `refactor_guide.md` 完成阶段 1、2、3、4、5、6、7、8、9、10 的主要重构。

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
- 新增 `src/models/secondclass_mapper.py`，集中 `SecondClass <-> DB row` 转换。
- 新增 `src/models/secondclass_view.py`，集中展示字段读取和格式化辅助函数。
- `src/models/activity.py` 收敛为兼容导出层，保留旧导入路径。
- `SecondClassDB` 快照写入改为复用 mapper，避免写入 row 逻辑继续分散。
- `ActivityRepository` 新增 row 级读取接口，供 diff 等稳定字段比较场景使用。
- `DiffEngine` 改为直接比较数据库 row 中的稳定字段，不再为 diff 构造完整 `SecondClass`。
- mapper 双向覆盖 `place_info`、`participation_form`、`children_id`、`parent_id`；`deep_scaned` 等扫描元数据只保留在数据库 row，不写入 `SecondClass.data`。
- 新增阶段 8 回归测试：`tests/test_refactor_stage_8.py`。
- 新增 `src/feishu_bot/card_builder.py`，集中活动列表飞书卡片、按钮、分页卡片构建逻辑。
- `src/utils/formatter.py` 不再承载卡片 schema，也不再兼容导出卡片 builder。
- 新增 `src/notifications/builders.py`，将筛选详情、新活动卡片请求、已报名变更、版本更新通知文案从监听器中拆出。
- `NotificationService` 改为只通过 `ActivityListCardRequest` 触发活动卡片构建并负责发送，`send_card()` 直接发送既有卡片仍可用。
- `Response.activity_list()` 不再提前构建卡片，只携带 `ActivityListCardRequest` 和非卡片构建 metadata，避免 `send_response()` 二次构建导致配置或分页规则不一致。
- 移除未使用的 `MessageSender` 兼容层。
- 移除 `send_response()` 中旧 `metadata["activities"]` fallback 和 `card_builder.build_activity_card(...)` 顶层兼容函数。
- 新增阶段 10 回归测试：`tests/test_refactor_stage_10.py`。
- `SecondClassDB` 为 `all_secondclass` 创建 `status`、`name`、`scan_timestamp`、`parent_id` 基础索引。
- 新增 `src/core/search_index.py`，集中 SQLite FTS5 trigram 能力探测、FTS 表创建和重建。
- `ActivityRepository.search(...)` 支持 `name_like` 与 `full_text` 两种模式，默认继续保持标题中文子串搜索；`full_text` 不可用或关键词过短时自动回退。
- 快照写入 `all_secondclass` 时同步维护 FTS 表，旧数据库在首次 full_text 搜索时可自动创建并重建。
- 新增 `search.mode` 配置项，显式开启 full_text 时搜索标题、组织单位、标签、活动构想和地点。
- 新增阶段 9 回归测试：`tests/test_refactor_stage_9.py`。

## 验证

- `/home/amsors/anaconda3/envs/pyustc/bin/python -m compileall src tests` 通过。
- `/home/amsors/anaconda3/envs/pyustc/bin/python -m unittest discover -s tests -v` 通过，25 个测试全绿。
- `git diff --check` 通过。

## 注意

- 沙箱内运行 `aiosqlite` 相关测试会卡住，最终单测是在沙箱外执行通过的。
- 未手动触发真实 USTC/飞书链路。
