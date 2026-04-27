# NextArc 重构实施指南

本文档将重构拆分为可独立开发、独立测试、验证通过后再进入下一阶段的工作包。原则是先固定可验证行为，再处理确定性问题，然后建立可复用边界并迁移调用方；每个阶段都应保持项目可启动、主流程可手动验证。

## 总体目标

0. 明确部署模型：NextArc 是具有敏感权限的私人机器人服务，每个用户应独立部署专门服务自己的机器人实例；本项目不为多用户共享部署、多机器人租户隔离或跨用户上下文隔离预留开发空间。
1. 降低核心链路耦合：扫描、数据访问、筛选、通知、机器人指令分别形成清晰边界。
2. 提升功能复用：定时扫描、`/valid`、`/search`、新活动通知、上下文相关指令复用同一套服务。
3. 优化数据路径：集中 SQLite 查询、写入和 `SecondClass` 转换，减少分散 SQL。
4. 统一筛选行为：消除 scanner 和 `/valid` 中重复筛选代码，避免入口不同导致结果不一致。
5. 重构上下文管理：为后续更多上下文相关指令提供统一状态、过期、分页、确认、展示结果管理能力。
6. 修复已知风险点：地点显示错误、筛选逻辑重复、后台通知失败不可见、全局配置读取分散、Handler 类变量依赖等。
7. 进行必要性能优化：批量写入、批量偏好操作、并发深度更新、搜索优化、减少不必要数据库读取。
8. 保持直接使用 `pyustc.young.SecondClass` 作为活动对象，不新增内部 `Activity` 模型替代它。
9. 统一活动操作链路：报名、取消报名、卡片报名、日历同步和报名后数据刷新应复用同一服务边界。

## 行为变化风险标记

重构过程中默认尽量保持旧行为。以下事项是有意修正或统一语义，可能“不完全保持旧行为”，实施时必须在 PR/提交说明中单独标记，并补充验证：

1. **地点显示修复**：当前有 `place_info` 时反而显示“未提供”；同时数据库行转 `SecondClass` 时没有把 `place_info` 回填到 `placeInfo`，导致来自快照数据库的活动即使修复展示判断也可能仍显示不出地点。修复后用户可见输出会变化，这是明确 bugfix。
2. **感兴趣白名单语义统一**：当前新活动通知会先恢复感兴趣活动，再执行已报名、重叠、时间、AI 等筛选，因此感兴趣活动可能绕过后续用户侧筛选，甚至绕过已报名过滤；`/valid` 只在数据库筛选阶段保留，后续仍可能被 overlay/time/AI 过滤。统一 pipeline 后定义为“感兴趣活动绕过偏好、重叠、空闲时间、AI 等用户侧筛选”，但不绕过硬业务约束，例如活动状态过滤、已报名过滤。这会改变 `/valid` 和新活动通知的部分结果，这是预期范围内的正确做法。
3. **通知错误传播**：当前后台通知失败多为日志可见，扫描结果不可见。改为可等待发布时，`ScanResult.notification_errors` 可记录通知失败；保持后台发布时，错误只能通过任务结果和日志记录，不承诺同步出现在已返回的扫描结果中。
4. **`/valid 深度` 并发更新**：从顺序更新改为 `SecondClassBatchUpdater` 后，失败顺序、日志顺序和耗时会变化，但返回语义应保持。
5. **搜索增强**：基础 `LIKE` 行为必须兼容；如果开启 FTS/full text，结果排序和匹配范围可能变化，必须通过配置显式启用。

本轮重构不为活动快照数据库引入完整 schema 版本标识或迁移框架。新增索引或 FTS 表只在对应阶段以向后兼容方式创建，不能要求历史活动快照数据库执行显式版本迁移。用户偏好数据库是长期持久化数据库，允许引入轻量 `meta(schema_version)` 记录，但不引入复杂迁移框架。

## 阶段 0：建立基线与回归检查

### 目标

在正式改结构前固定当前行为，保证后续每一阶段都有可验证标准。

### 任务

1. 梳理当前可手动验证的主流程：
   - 启动应用。
   - 执行 `/alive`。
   - 执行 `/check` 或 `/update`。
   - 执行 `/valid`、`/valid 全部`、`/valid 重新扫描`、`/valid 深度`。
   - 执行 `/search 关键词`。
   - 对活动执行“不感兴趣”“感兴趣”。
   - 对可报名活动执行报名、取消报名。
   - 触发新活动通知卡片展示。
   - 点击卡片按钮：不感兴趣、感兴趣、去报名、查看子活动。
2. 增加最小自动化测试基础，优先覆盖纯函数和不依赖真实 USTC/飞书的逻辑：
   - 活动格式化。
   - 时间筛选和重叠筛选。
   - 数据库行与 `SecondClass` 对象转换。
   - 用户偏好互斥逻辑。
   - 序号解析和上下文过期。
   - 如果选择 `pytest`，需要新增 `pytest` 和 `pytest-asyncio` 测试依赖；如果不新增依赖，则使用标准库 `unittest` 和 `IsolatedAsyncioTestCase`。
3. 记录当前数据库表结构和配置项，避免后续阶段误改兼容性。

### 验证

1. 在 `pyustc` conda 环境中运行导入检查：
   - `python -m compileall src`
2. 手动运行一次启动流程。
3. 至少执行 `/alive`、`/valid 全部`、`/search`。

### 完成标准

有一份可重复的“阶段后验证清单”，后续每阶段都按同一清单验证。

## 阶段 1：修复明确风险点与小范围性能问题

### 目标

在大规模拆分前修复确定性问题，并完成不会影响架构边界的小性能优化。

### 任务

1. 修复地点显示逻辑：
   - 当前 `format_secondclass_for_list` 中地点判断写反。
   - 应为有 `place_info` 时显示地点，无地点时显示“未提供”。
   - 同步修复数据库 row 到 `SecondClass` 的最小 mapper 问题：`place_info` 必须回填为 `placeInfo`，`participation_form` 必须回填为 `form`，否则快照数据库读取出的活动仍无法正确展示地点和参与形式。
   - 此处只做最小兼容修复，完整 mapper 模块仍放到阶段 8。
   - **行为变化风险**：用户可见文本会变化，这是 bugfix。
2. 批量偏好操作改为单事务：
   - `add_ignored_activities` 不再逐个调用 `remove_interested_activity`。
   - `add_interested_activities` 不再逐个调用 `remove_ignored_activity`。
   - 使用 `DELETE ... WHERE activity_id IN (...)` 和 `executemany`。
   - 单个 `add_ignored_activity` / `add_interested_activity` 也应在同一事务中保证互斥，避免未来调用方绕过 toggle 时产生双表状态。
3. `SecondClassDB` 写入改为 `executemany`：
   - `update_all_secondclass`
   - `update_enrolled_secondclass`
   - 保持现有备份/恢复语义不变。
   - 如果同步 `sqlite3` 写入仍会明显阻塞事件循环，后续阶段再切换为 `aiosqlite` 或 `asyncio.to_thread()` 包裹写入；本阶段先不扩大改动面。
4. `/valid 深度`、`/search` 深度刷新、查看子活动刷新统一复用 `SecondClassBatchUpdater`，避免顺序更新。
5. 将裸 `except:` 改为显式异常捕获，至少覆盖 `UserPreferenceManager` 中的裸捕获。
6. 明确 `SecondClassBatchUpdater` 的失败策略语义：
   - 如果保留当前 `asyncio.gather` 全量执行模式，`continue_on_error=False` 只能影响返回结果处理，不能声称是 fail-fast。
   - 如果需要真正 fail-fast，应在本阶段修正实现或暂不暴露该语义。

### 验证

1. 格式化和 mapper 测试覆盖有地点、无地点、有参与形式、无参与形式四种情况。
2. 偏好互斥测试：
   - 添加不感兴趣会从感兴趣移除。
   - 添加感兴趣会从不感兴趣移除。
   - 批量操作保持互斥。
   - 单个 add/toggle 操作也保持互斥。
3. 手动验证 `/preference`、`不感兴趣 全部`、`感兴趣 序号`。
4. 手动验证 `/valid 深度` 和 `/search` 不阻塞过久，失败活动会记录 warning 但不影响整体返回。

### 完成标准

确定性 bug 得到修复；性能优化不改变核心业务语义。

## 阶段 2：集中数据访问层

### 目标

把分散在 scanner、handler、filter、diff、preference manager 中的 SQLite 查询集中起来，先不改变业务判断。

### 边界约定

1. `ActivityRepository` 负责活动快照数据库的只读查询，并返回 `SecondClass` 或轻量查询结果。
2. `PreferenceRepository` 负责用户偏好数据库的基础 CRUD，不包含业务筛选策略。
3. `SnapshotWriter` 或保留 `SecondClassDB` 负责快照写入；不要把写快照和读查询都塞进同一个 repository。
4. `UserPreferenceManager` 可以暂时作为业务服务保留，内部逐步委托 `PreferenceRepository`。

### 新增模块建议

```text
src/core/repositories/
├── __init__.py
├── activity_repository.py
├── preference_repository.py
└── snapshot_writer.py
```

### 核心接口草案

```python
class ActivityRepository:
    async def count_all(self, db_path: Path) -> int: ...
    async def count_enrolled(self, db_path: Path) -> int: ...
    async def list_valid(self, db_path: Path) -> list[SecondClass]: ...
    async def search_by_name(self, db_path: Path, keyword: str) -> list[SecondClass]: ...
    async def get_by_ids(self, db_path: Path, activity_ids: list[str]) -> list[SecondClass]: ...
    async def list_enrolled_ids(self, db_path: Path) -> set[str]: ...
    async def list_enrolled_time_ranges(self, db_path: Path) -> list[EnrolledActivityTime]: ...
```

`get_by_ids()` 必须保持输入 ID 顺序，缺失活动可跳过但不得重新按数据库默认顺序返回，避免通知、新活动 diff、偏好恢复等展示顺序发生隐性变化。

```python
class PreferenceRepository:
    async def initialize(self) -> None: ...
    async def get_ids(self, kind: PreferenceKind) -> set[str]: ...
    async def add_many(self, kind: PreferenceKind, activity_ids: list[str]) -> tuple[int, int]: ...
    async def remove_many(self, kind: PreferenceKind, activity_ids: list[str]) -> int: ...
    async def count(self, kind: PreferenceKind) -> int: ...
```

### 任务

1. 将以下查询迁入 `ActivityRepository`：
   - scanner 中活动计数、已报名计数。
   - `/valid` 中有效活动查询。
   - `/search` 中名称搜索。
   - `/info` 中已报名活动查询。
   - `OverlayFilter.get_enrolled_time_ranges_from_db`。
   - `EnrolledFilter.get_enrolled_ids_from_db`。
   - `DiffEngine.get_enrolled_ids`。
2. 保留旧方法作为薄包装，避免一次性修改过大。
3. 为 repository 增加单元测试，使用临时 SQLite 文件构造小数据集。
4. 统一 row factory 和 `secondclass_from_db_row` 调用位置。
5. `PreferenceRepository` 不接受任意表名字符串，使用 `PreferenceKind` 枚举或内部白名单映射到具体表，避免 SQL 表名拼接继续扩散。
6. 用户偏好数据库可以新增轻量 `meta(schema_version)` 表，用于记录长期持久化数据库的兼容状态；本阶段不引入完整迁移框架。

### 性能优化

1. 查询只取需要字段：
   - count 查询不反序列化整行。
   - enrolled ids 只取 `id`。
   - enrolled time ranges 只取 `hold_time`、`name`、`participation_form`。
2. 搜索阶段先保持 `LIKE` 行为不变，后续阶段再引入 FTS 或索引。

### 验证

1. `python -m compileall src`
2. repository 单元测试通过。
3. 手动验证 `/valid`、`/search`、`/info` 结果和重构前一致。

### 回滚边界

如果 repository 行为异常，可以让旧调用方继续走原 SQL；本阶段不应修改业务判断。

## 阶段 3：活动用例服务、深度更新服务与报名服务

### 目标

在 Handler 和底层 repository 之间建立用例服务，避免 Handler 直接编排“查询、更新、筛选、上下文保存、展示配置”。

### 建议模块

```text
src/core/services/
├── __init__.py
├── activity_query_service.py
├── activity_update_service.py
├── enrollment_service.py
└── preference_service.py
```

### 边界约定

1. Repository 只处理数据访问。
2. `ActivityQueryService` 处理 `/valid`、`/search`、`/info` 需要的活动查询用例。
3. `ActivityUpdateService` 统一处理 `SecondClass.update()` 的并发深度更新和失败策略。
4. `EnrollmentService` 统一处理报名、取消报名、卡片报名、报名后日历同步和必要的数据刷新策略。
5. `PreferenceService` 或保留 `UserPreferenceManager` 处理偏好互斥、白名单恢复、AI 缓存读写等业务规则。

### 任务

1. 将 `/valid`、`/search`、`/info` 中直接 SQL 查询替换为 `ActivityQueryService`。
   - 本阶段只统一查询和深度更新入口，不迁移 `/valid` 的筛选编排，避免在 pipeline 落地前复制新的筛选流程。
2. 将 `/valid 深度`、`/search` 活动更新、卡片“查看子活动”更新替换为 `ActivityUpdateService`。
3. 统一深度更新参数：
   - 最大并发数。
   - 是否失败继续。
   - 失败日志格式。
   - 是否由服务内部创建 `auth_manager.create_session_once()` 上下文。默认建议由 `ActivityUpdateService` 负责创建认证上下文，调用方只传入活动列表和更新选项，避免 Handler、卡片处理器继续重复管理 CAS session。
4. 明确深度更新持久化语义：
   - 扫描/同步链路的深度更新写入快照数据库。
   - 查询展示链路的深度更新默认只更新内存对象，不回写快照。
   - 如后续需要查询链路回写，应显式提供 `persist=True` 并通过 repository/writer 处理。
5. 新增或规划 `EnrollmentService`：
   - `/join`、`/cancel` 和卡片报名/取消报名复用同一服务。
   - 统一状态检查、`SignInfo` 获取、`SecondClass.apply()` / `cancel_apply()` 调用、错误消息、日历同步。
   - 报名或取消成功后明确是否触发已报名活动刷新；如果不刷新，应在返回消息或后续阶段中标记为待处理。
   - 保留当前 `/join` 默认基于搜索结果序号的行为；如果要支持 `/valid` 后直接 `/join 序号`，应作为行为增强单独标记并测试。
6. 保留 Handler 中的参数解析和 Response 组装，不让 Handler 继续直接拼数据库查询或直接编排报名细节。

### 验证

1. `/valid`、`/valid 深度`、`/search`、`/info` 输出可用。
2. 模拟单个活动 update 失败时，其他活动仍正常展示。
3. 卡片查看子活动仍能展示可报名子活动。
4. `/join`、`/cancel` 和卡片报名的成功/失败行为与重构前一致。

### 完成标准

Handler 不再直接访问 SQLite；深度更新入口统一；报名/取消报名的核心操作开始向统一服务收口。

## 阶段 4：统一活动筛选管线

### 目标

消除 scanner 和 `/valid` 中重复筛选代码，让所有入口使用同一条筛选流程。

### 建议模块

```text
src/core/filtering/
├── __init__.py
├── pipeline.py
├── context.py
└── result.py
```

### 接口草案

```python
@dataclass
class FilterContext:
    latest_db: Path
    enable_filters: bool = True
    include_interested_restore: bool = True
    use_ai_cache: bool = True
    force_ai_review: bool = False
    ignore_overlap: bool = False
    filter_config: FilterConfig | None = None
    ai_config: AIFilterRuntimeConfig | None = None
    source: str = "unknown"
```

```python
@dataclass
class FilterPipelineResult:
    kept: list[SecondClass]
    filtered: dict[str, list[FilteredActivity]]
    restored: list[SecondClass]
    ai_keep_reasons: dict[str, str]
    overlap_reasons: dict[str, str]
    summaries: list[str]
```

```python
class ActivityFilterPipeline:
    async def apply(
        self,
        activities: list[SecondClass],
        context: FilterContext,
    ) -> FilterPipelineResult: ...
```

### 任务

1. 管线顺序统一为：
   - 硬业务约束过滤：活动状态必须满足当前入口要求，例如 `/valid` 和新活动推荐只保留可报名/已发布等允许展示的状态。
   - 已报名过滤。
   - 感兴趣白名单恢复。
   - 不感兴趣数据库过滤。
   - 已报名时间重叠过滤或标注。
   - 自定义空闲时间过滤。
   - AI 筛选。
2. 把 `/valid` 中 enrolled/db/overlay/time/ai 逻辑迁移到 pipeline。
3. 把 scanner 新活动通知中的相同逻辑迁移到 pipeline。
4. 明确定义白名单活动语义：
   - 活动状态过滤和已报名过滤属于硬业务约束，必须发生在感兴趣白名单恢复之前，感兴趣白名单不得绕过。
   - 通过硬约束后的感兴趣活动从待筛选列表中移出。
   - 感兴趣活动直接进入最终保留列表。
   - 感兴趣活动绕过不感兴趣偏好、重叠、空闲时间、AI 等用户侧筛选。
   - **行为变化风险**：修正 `/valid` 与新活动通知当前不一致的行为。
5. 统一筛选结果摘要生成，避免每个入口拼不同文案。
6. 将 `overlay` 加入可恢复/可展示的筛选类型设计；`enrolled` 作为硬业务约束只进入可展示筛选结果，不提供通过“感兴趣”恢复的语义，避免通知展示了筛选结果但指令无法解释。
7. 新建 pipeline、context、result 时不得内部调用 `get_settings()`；`ignore_overlap`、AI 缓存策略、通知展示需要的配置均通过 `FilterContext` 或构造函数显式传入。

### 验证

1. 使用同一批活动，比较 `/valid` 和新活动通知的筛选结果一致性。
2. 测试不可报名状态活动、已报名活动会先被硬约束排除，即使它们在感兴趣列表中也不会进入最终展示。
3. 测试白名单活动不会被时间/AI/重叠/忽略过滤，但仍会被已报名或不可报名状态等硬业务约束排除。
4. 测试 `ignore_overlap=true/false` 两种配置。
5. 测试 `重新筛选` 会绕过 AI 缓存。
6. 测试 `/interested ai|db|time|overlay 全部` 等恢复指令符合预期。

### 完成标准

scanner 和 `/valid` 不再直接编排各筛选器，只调用 `ActivityFilterPipeline.apply()`。

## 阶段 5：重构上下文管理模块

### 目标

为后续更多上下文相关指令提供统一能力，不再让 `UserSession` 同时承载搜索结果、展示结果、确认状态和零散扩展字段。

本阶段仍按“单实例、单用户、单机器人”设计。上下文管理只服务当前部署实例，不实现用户分区、租户隔离、多机器人上下文隔离，也不为这些场景保留额外抽象。

### 建议模块

```text
src/context/
├── __init__.py
├── models.py
├── manager.py
├── store.py
└── policies.py
```

### 核心设计

上下文分为几类：

1. `displayed_activities`：最近展示给用户的活动列表，用于“报名 序号”“不感兴趣 序号”等。
2. `search_result`：搜索结果，可带关键词、过期时间。
3. `confirmation`：二次确认操作，如报名、取消、升级。
4. `preference_view`：偏好页上下文，后续可支持“移除第 N 个偏好”。
5. `conversation_state`：预留给后续多轮指令，例如配置修改、筛选条件临时保存。

### 接口草案

```python
from enum import Enum
from typing import Generic, TypeVar


T = TypeVar("T")


class ContextType(str, Enum):
    DISPLAYED_ACTIVITIES = "displayed_activities"
    SEARCH_RESULT = "search_result"
    CONFIRMATION = "confirmation"
    PREFERENCE_VIEW = "preference_view"
    CONVERSATION_STATE = "conversation_state"
```

```python
@dataclass
class ContextRecord(Generic[T]):
    type: ContextType
    payload: T
    created_at: datetime
    expires_at: datetime | None = None
    source: str | None = None
```

以上接口草案必须保持 Python 3.10 兼容，不使用 Python 3.11 的 `StrEnum` 或 Python 3.12 的 `class X[T]` 泛型类语法。

```python
class ContextManager:
    async def set(self, record: ContextRecord) -> None: ...
    async def get(self, type: ContextType) -> ContextRecord | None: ...
    async def clear(self, type: ContextType | None = None) -> None: ...
    async def cleanup_expired(self) -> int: ...
```

### 任务

1. 把当前 `UserSession` 中的上下文相关字段迁移到 `ContextManager`。
2. 保留 `UserSession` 中确实与外部服务交互有关的身份字段：
   - `user_id`
   - 如现有飞书 SDK 回调需要，也可保留 `open_id`、`chat_id` 等字段，但它们不用于上下文分区。
   - 连接状态相关信息。
3. 将以下调用改为通过 `ContextManager`：
   - `session.set_search(...)`
   - `session.set_displayed_activities(...)`
   - `session.confirm`
   - `session.clear_confirm()`
4. `MessageRouter._handle_confirmation` 改为读取 confirmation context。
5. 通知监听器保存新活动上下文时也通过 `ContextManager`，不直接写 `UserSession`。
6. 为上下文过期策略写测试：
   - 搜索结果默认 5 分钟。
   - 确认操作默认较短过期，例如 2 分钟。
   - 展示活动可独立设置过期时间。
7. 暂时使用内存 store：
   - `InMemoryContextStore`
   - 如后续仅为单用户实例提供跨重启恢复，再实现 `SQLiteContextStore`。

### 验证

1. `/search` 后执行 `/join 序号`。
2. `/valid` 后执行“不感兴趣 序号”“感兴趣 序号”。
3. 新活动通知后执行“不感兴趣 序号”。
4. 报名和取消报名确认流程正常。
5. 搜索结果过期后按原有行为提示过期。
6. 如果新增 `/valid` 后直接 `/join 序号`，应单独作为行为增强验证；否则本阶段不得改变 `/join` 只操作搜索结果的既有语义。

### 完成标准

所有上下文相关行为从单实例 `ContextManager` 读取，`UserSession` 不再承载业务上下文；没有新增多用户或多机器人隔离抽象。

## 阶段 6：拆分扫描编排与通知事件

### 目标

让扫描器只承担“定时触发和兼容入口”，把拉取、快照写入、diff、事件发布分成独立服务。

### 建议模块

```text
src/core/scanning/
├── __init__.py
├── coordinator.py
├── sync_service.py
├── diff_service.py
├── scheduler.py
└── result.py
```

### 接口草案

```python
class ActivitySyncService:
    async def sync(self, target_db: Path, deep_update: bool) -> SyncResult: ...
```

```python
class ScanCoordinator:
    async def scan(self, options: ScanOptions) -> ScanResult: ...
```

```python
@dataclass
class ScanOptions:
    deep_update: bool
    notify_diff: bool
    notify_enrolled_change: bool
    notify_new_activities: bool
    no_filter: bool
    wait_for_notifications: bool = False
```

### 任务

1. 从 `ActivityScanner._do_scan` 中抽出：
   - 数据抓取和写入。
   - diff 计算。
   - enrolled change 生成。
   - new activities 筛选和事件生成。
2. 后台发布新活动事件不再静默吞失败：
   - `EventBus.publish()` 返回 listener 执行结果，或提供 `publish_with_result()`。
   - `NotificationListener` 发送失败需要向事件总线返回失败或抛出可聚合异常，而不只是内部日志。
   - 注意当前失败会在三层被吞掉：`EventBus._invoke_listener()`、`NotificationListener` 的发送分支、scanner 的后台发布包装。实现等待通知结果时必须同时调整这三层，否则 `notification_errors` 仍然拿不到真实失败。
   - 建议定义轻量 `EventPublishResult` / `ListenerResult`，记录 listener 名称、成功状态、异常信息；后台发布时也应在任务完成回调中记录该结果。
   - 当 `ScanOptions.wait_for_notifications=True` 时，扫描流程等待通知 listener 完成，并将失败写入 `ScanResult.notification_errors`。
   - 当保持后台发布时，扫描结果不承诺同步包含通知失败；后台任务必须记录任务结果和错误日志，避免完全静默。
   - **行为变化风险**：启用等待通知后，`/check`、日志和扫描结果中可能出现过去被吞掉的通知错误，且 `/check` 耗时可能增加。
3. 版本检查调度从 `ActivityScanner.start()` 拆到独立 `VersionScheduler` 或 `MaintenanceScheduler`。
4. 保留外部兼容方法 `scanner.scan(...)`，内部委托给新 coordinator，降低调用方迁移风险。

### 验证

1. 手动 `/check` 仍能生成新数据库。
2. 有旧数据库时能生成 diff。
3. 新活动事件仍能触发通知。
4. 模拟通知异常：
   - `wait_for_notifications=True` 时扫描结果中能看到错误。
   - 后台发布时日志中有明确任务错误，不再完全静默。

### 完成标准

`ActivityScanner` 文件明显变薄，只负责定时任务生命周期和兼容入口。

## 阶段 7：应用上下文与依赖注入改造

### 目标

替换 Handler 类变量依赖和散落的 `get_settings()`，让服务依赖可测试、可替换、可扩展。

### 建议模块

```text
src/app/
├── __init__.py
├── context.py
└── factory.py
```

### 接口草案

```python
@dataclass
class AppContext:
    settings: Settings
    preferences: PushPreferences
    auth_manager: AuthManager
    db_manager: DatabaseManager
    activity_repo: ActivityRepository
    preference_manager: UserPreferenceManager
    context_manager: ContextManager
    activity_query_service: ActivityQueryService
    activity_update_service: ActivityUpdateService
    filter_pipeline: ActivityFilterPipeline
    scanner: ActivityScanner
```

### 任务

1. `NextArcApp.initialize()` 改为构建 `AppContext`。
2. `MessageRouter` 构造函数接收 `AppContext`。
3. Handler 构造函数接收 `AppContext` 或更窄依赖，移除：
   - `CommandHandler.set_dependencies`
   - `ValidHandler.set_ignore_manager`
   - `AliveHandler.set_ignore_manager`
   - `IgnoreHandler.set_ignore_manager`
   - `InterestedHandler.set_user_preference_manager`
   - `PreferenceHandler.set_dependencies`
4. `NotificationListener` 构造函数接收需要的配置，不再内部调用 `get_settings()`。
5. `NotificationService.send_activity_list_card` 接收明确的卡片配置，不再内部读取全局 settings。
6. `CardActionHandler` 构造函数接收依赖，替代二次 `set_dependencies`。
7. 保留 `src.config.get_settings()` 作为兼容层，但新代码不再主动使用。
8. 配置收口不是只在本阶段才开始：
   - 阶段 4 的筛选管线必须通过显式配置运行。
   - 阶段 6 的扫描协调器必须通过 `ScanOptions` 和构造参数运行。
   - 阶段 10 的通知/card builder 必须通过显式卡片配置运行。
   - 本阶段负责清理剩余旧调用点和 handler 初始化方式。

### 验证

1. 所有指令 handler 能初始化。
2. `/help` 指令列表完整。
3. `/alive`、`/valid`、`/search`、`/ignore`、`/interested` 正常。
4. 卡片按钮“不感兴趣”“感兴趣”“去报名”“查看子活动”正常。

### 完成标准

Handler 不再使用类变量保存运行时依赖；新增代码不再主动调用全局 `get_settings()`。

## 阶段 8：pyustc 使用边界整理

### 目标

不重写活动数据模型，继续直接使用 `pyustc.young.SecondClass`。本阶段只整理 `SecondClass` 的创建、更新、数据库行转换和展示适配位置，避免这些辅助逻辑分散在 handler、repository、formatter 中。

### 建议模块

```text
src/models/
├── activity.py              # 保留现有 SecondClass 兼容工具
├── secondclass_mapper.py    # 集中 SecondClass <-> 数据库行转换
└── secondclass_view.py      # 集中展示字段读取和格式化辅助
```

### 边界约定

1. 业务层、筛选器、通知卡片、AI 筛选继续接收和返回 `SecondClass`。
2. 数据库读取统一通过 repository 返回 `SecondClass`。
3. 数据库写入统一通过 mapper 将 `SecondClass` 转为 row。
4. 不新增 `Activity`、`ActivityViewModel` 等替代模型。
5. 如果为了测试需要构造活动，应优先使用 `SecondClass.from_dict(...)`。

### 任务

1. 将 `secondclass_from_db_row` 和 `SecondClassDB._secondclass_to_row` 迁移或包装到统一 mapper。
2. 保持 `src/models/activity.py` 对外兼容，避免一次性改大量 import。
3. 补齐 mapper 对现有字段的双向转换，尤其是：
   - `place_info`
   - `participation_form`
   - `children_id`
   - `parent_id`
   - `deep_scaned` 相关元数据只作为数据库元数据，不强行塞进 `SecondClass`。
   - `place_info -> placeInfo` 和 `participation_form -> form` 的最小修复已要求在阶段 1 完成；本阶段负责把这些兼容逻辑正式收口到 mapper，避免再次分散。
4. 将展示字段读取函数集中整理：
   - `get_display_time`
   - `get_status_text`
   - `get_apply_progress`
   - `get_module_name`
   - `get_department_name`
   - `get_place_info`
   - `get_participation_form`
5. diff 可以直接比较数据库 row 中的稳定字段，避免为了比较而构造完整 `SecondClass`；但 diff 输出中如需要活动对象，仍使用 `SecondClass.from_dict(...)`。
6. 增加测试，使用 `SecondClass.from_dict(...)` 构造样例活动，验证 mapper 和展示辅助函数。

### 验证

1. diff 测试覆盖新增、删除、字段变化。
2. formatter 输出与迁移前一致，除了已明确修复的地点显示。
3. `/valid`、`/search` 输出一致。

### 完成标准

项目仍直接使用 `pyustc.young.SecondClass`，但转换和展示辅助逻辑集中，handler 和 scanner 中不再散落 row 解析细节。

## 阶段 9：搜索与索引优化

### 目标

改善搜索性能和搜索能力，同时保持现有 `/search <关键词>` 行为兼容。

### 任务

1. 为 `all_secondclass` 增加基础索引：
   - `status`
   - `name`
   - `scan_timestamp`
   - `parent_id`
   - 注意：当前默认搜索如果仍使用 `LOWER(name) LIKE '%keyword%'`，普通 `name` B-tree 索引通常不能带来主要性能收益；基础索引主要服务状态查询、排序、前缀/精确查询和后续扩展。
2. 评估并可选引入 SQLite FTS5：
   - 标题 `name`
   - 组织单位 `department`
   - 标签 `labels`
   - 活动构想 `conceive`
   - 地点 `place_info`
   - 中文搜索必须单独验证 tokenizer 行为。SQLite FTS5 默认 tokenizer 未必等价于当前 `LIKE '%keyword%'` 的中文子串匹配；若使用 `trigram` 等 tokenizer，必须检测运行环境是否支持并提供自动降级。
3. `ActivityRepository.search(...)` 支持搜索模式：
   - `name_like`：默认模式，保持旧行为。
   - `full_text`：可通过配置显式启用。
4. 写入快照时同步维护 FTS 表；数据库不存在 FTS 表时自动创建或降级。
5. 不引入数据库版本标识或迁移框架。
6. 性能目标以 FTS/full text 或明确可用索引的查询模式为主，不把普通 `LIKE '%keyword%'` 的加速作为阶段完成条件。
7. 默认 `name_like` 模式必须继续覆盖当前中文子串搜索场景；`full_text` 不能作为默认替代，除非已有测试证明结果不减少。

### 验证

1. 默认模式下旧搜索关键词结果不减少。
2. 中文关键词可搜索。
3. 中文子串搜索在默认模式下与旧 `LIKE` 行为一致。
4. 数据库不存在 FTS 表时能自动创建或降级。
5. 开启 FTS/full text 后，大量活动数据下搜索耗时明显低于旧实现。
6. **行为变化风险**：开启 `full_text` 后结果排序和匹配范围允许变化，但必须由配置显式开启。

### 完成标准

默认行为兼容，开启 FTS 后搜索更快且范围更广。

## 阶段 10：通知与卡片构建解耦

### 目标

减少通知监听器和 formatter 的耦合，让通知内容构建、卡片构建、发送通道分离。

### 建议模块

```text
src/notifications/
├── builders.py
├── listener.py
├── service.py
└── feishu_service.py

src/feishu_bot/
├── card_builder.py
└── card_handler.py
```

### 任务

1. 将 `NotificationListener.on_new_activities_found` 中的消息拼接迁移到 builder。
2. 将飞书卡片构建从 `utils.formatter` 迁移到更明确的 `feishu_bot/card_builder.py`。
3. `NotificationService` 只负责发送，不负责内容构建和配置读取。
4. 新活动通知、筛选详情通知、版本通知分别有独立 builder。
5. 卡片分页、按钮配置、AI reason、overlap reason 的展示规则统一由 builder 接收显式配置。
6. 同步理清 `Response.activity_list()` 与 `NotificationService.send_response()` 的职责：
   - 当前 `Response.activity_list()` 会先构建卡片，同时 metadata 中又携带 activities。
   - `send_response()` 看到 activities 后会再次调用 `send_activity_list_card()` 构建卡片。
   - 拆出 card builder 时必须改为单一构建路径，避免卡片配置、分页、忽略状态、AI reason 或 overlap reason 在两处出现不一致。

### 验证

1. 新活动卡片展示完整。
2. `send_ai_filter_detail.filtered` 和 `kept` 两个配置仍生效。
3. `notify_filtered_activities=false` 时不发送筛选详情文本。
4. 卡片分页时序号连续，`不感兴趣 序号` 仍能操作最近展示列表。
5. `Response.activity_list()` 经 `send_response()` 发送时只构建一次卡片，直接 `send_card()` 的路径也仍可用。

### 完成标准

监听器只负责响应事件和调用 builder/service，不直接拼复杂文案。

## 阶段 11：清理兼容层与文档更新

### 目标

删除过渡期遗留接口，更新开发文档，让后续开发遵循新架构。

### 任务

1. 删除或标记废弃：
   - `IgnoreManager` 旧兼容模块。
   - Handler classmethod 依赖注入接口。
   - scanner 中仅为兼容保留的内部包装方法。
   - filter 中直接访问数据库的旧静态方法。
2. 更新 `AGENTS.md` 和 README 中的架构描述。
3. 增加“新增指令”的新流程：
   - Handler 接收 `AppContext` 或所需窄依赖。
   - 如需上下文，使用 `ContextManager`。
   - 如需活动查询，使用 `ActivityQueryService` 或 `ActivityRepository`。
   - 如需筛选，使用 `ActivityFilterPipeline`。
   - 如需报名、取消报名或报名后日历同步，使用 `EnrollmentService`。
4. 增加“新增筛选器”的新流程：
   - 实现 pipeline step。
   - 返回统一 `FilteredActivity`。
   - 补充对应测试。

### 验证

1. 全量导入检查。
2. 所有手动主流程通过。
3. 文档中的新增指令流程可指导实现一个简单测试 handler。

### 完成标准

新架构成为唯一推荐路径，旧路径不再继续扩散。

## 每阶段通用验证清单

每完成一个阶段，至少执行：

1. `python -m compileall src`
2. 如已建立测试：运行单元测试。
3. 启动程序，确认初始化无异常。
4. 手动验证：
   - `/alive`
   - `/valid`
   - `/valid 全部`
   - `/search <已有关键词>`
   - 不感兴趣/感兴趣标记
   - 报名/取消报名确认流程
   - 新活动通知卡片和卡片按钮
5. 检查日志中是否出现新增 ERROR。

## 阶段依赖关系

推荐顺序：

1. 阶段 0：基线。
2. 阶段 1：确定性风险修复和小性能优化。
3. 阶段 2：数据访问层。
4. 阶段 8：pyustc 使用边界整理。
5. 阶段 3：活动用例服务、深度更新服务与报名服务。
6. 阶段 4：统一筛选管线。
7. 阶段 5：上下文管理。
8. 阶段 6：拆分扫描编排。
9. 阶段 7：依赖注入。
10. 阶段 10：通知与卡片解耦。
11. 阶段 9：搜索和索引优化。
12. 阶段 11：清理和文档更新。

其中阶段 0、1、2 是后续工作的基础，不建议跳过。阶段 1 必须先完成 `place_info -> placeInfo` 和 `participation_form -> form` 的最小 mapper 修复；阶段 8 再把 mapper 和展示辅助正式收口。阶段 8 建议提前到阶段 3、4 之前完成，因为 repository、service 和 pipeline 都会依赖 `SecondClass` 与数据库 row 的稳定转换边界。阶段 10 建议早于阶段 9 完成，先把通知/card builder 的配置读取收口，再做搜索展示能力扩展。阶段编号保留原方案编号，表示主题分组，不强制等同于实施顺序。活动快照数据库的完整 schema 版本/迁移框架不在本轮重构范围内；用户偏好数据库允许引入轻量 schema 版本记录。
