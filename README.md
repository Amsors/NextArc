# NextArc - 第二课堂活动监控机器人

自动监控 USTC 第二课堂活动变化，支持飞书机器人交互。

## 重要更新日志

**当前已初步支持机器人daemon化 & 通过脚本一键部署机器人。无需安装虚拟环境 / 折腾git仓库！**

[安装、迁移与升级脚本文档](./docs/install_and_migration.md)

[完整更新记录文档](./docs/change_log.md)

## 项目介绍

**NextArc** 是一款专为科大学生设计的第二课堂活动监控与辅助报名系统。解决第二课堂活动信息获取不及时、热门活动报名困难等问题。

我校的第二课堂系统具有以下问题：

- 新活动发布时没有主动向用户推送获知，需要学生手动刷新浏览
- 活动数量众多，难以筛选感兴趣的活动（活动的显示不是按照发布事件进行排序的......）
- 学生难以快速判断活动与课程/个人安排是否冲突

NextArc 可以帮你解决上述问题：

- **24小时自动监控**：定时扫描第二课堂系统，第一时间发现新活动
- **智能推送过滤**：支持已报名过滤、时间重叠过滤、时间筛选、AI 筛选和偏好标记等过滤机制
- **便利的交互方式**：通过飞书机器人完成查询、报名、取消等全部操作
- **个性化配置**：自定义空闲时间、AI筛选提示词，自定义数据刷新事件，自定义大模型提供方......

本项目为私人机器人，你需要在自己控制的计算机上部署只服务你的NextArc，开发者不提供公共服务

你的学号和密码都以存储在本机（并进行了用户隔离），你的姓名、学号、密码等所有信息都**不会**上传到除了我校CAS认证(`id.ustc.edu.cn`)、二课系统(`young.ustc.edu.cn`) 以外的**任何**服务器上，机器人本身不会以任何形式收集任何遥测信息。推送消息只会通过飞书SDK，经飞书的服务器推送给你，不经过开发者或其他任何第三方，无需担心隐私泄露。

## 风险提示
**目前的 NextArc daemon 安装已经进行了相当完善的权限隔离，但如因你的服务器被入侵等原因导致账号密码或其他隐私信息泄露，开发者不对任何后果承担任何负责。**

**请保证部署机器人的服务器完全由你控制，并对你的服务器采取包括但不限于以下的安全措施：**

- 配置使用证书的ssh登录
- 修改默认ssh端口号，安装fail2ban等软件防止爆破
- 只允许特定ip通过ssh连接
- 定期更新系统包

欢迎对本项目和 pyustc 项目进行安全审计。


## 功能说明

### 1. 自动活动扫描

- **定时扫描**：可配置扫描间隔（默认 15 分钟），自动检测第二课堂活动变化，获取的数据库记录在本地SQLite数据库中
- **差异对比**：自动对比新旧数据库，识别新增、修改、删除的活动
- **深度更新**：可一键深度更新当前所有二课的信息，包括报名人数等信息

### 2. 推送筛选

NextArc提供多样的筛选机制，确保只推送你可能会参与的活动：

| 筛选类型            | 说明                                                   | 优先级 |
|-------------------|------------------------------------------------------|-----|
| **感兴趣白名单**     | 用户主动标记为感兴趣的活动，绕过全部用户侧筛选；但不绕过不可报名 / 已报名等硬约束 | 最高  |
| **已报名筛选**       | 自动过滤已报名的活动，避免重复通知                                 | 高   |
| **不感兴趣黑名单**   | 用户主动标记为"不感兴趣"的活动，后续不再推送                          | 中   |
| **已有活动重叠筛选** | 检测待筛选的单次活动是否与已报名活动时间重叠；系列活动不参与此筛选；提交作品类活动不视为重叠 | 中   |
| **时间筛选**         | 根据用户配置的没空时间段，过滤时间冲突的活动                         | 中   |
| **AI 智能筛选**      | 基于大语言模型分析活动内容和用户偏好，推断是否感兴趣                 | 低   |

感兴趣白名单和不感兴趣黑名单均存储在本地数据库中，白名单的预期用途是强制绕过用户侧筛选因素，而非类似“Steam愿望单”的机制；它不会让已报名或不可报名活动重新进入推荐列表（例如，配置了周三下午16:00至18:00没空，但某个周三的一次保研经验分享二课你非常感兴趣，可以将此二课加入白名单，避免此活动因为时间重叠被筛选掉；又例如，你在发给大模型的提示词中写到“我对一切音乐相关二课不感兴趣”，但你偏偏对某一次音乐会二课感兴趣，可以将此二课加入白名单，避免此活动被AI判定为不感兴趣）

实际上“感兴趣”和“不感兴趣”的作用有限，由于我校二课活动众多，完全没有必要对每个活动都点一下感兴趣/不感兴趣

时间筛选有以下三种配置方式：

- `partial`（部分重叠）：活动时间与用户非空闲时间有任何交集，即过滤此二课（适合固定课程）
- `full`（完全包含）：活动时间完全落在非空闲时间段内，才过滤此二课
- `threshold`（比例阈值）：重叠时间占活动时长比例超过阈值，才过滤此二课

### 3. 飞书机器人交互

**只要完成机器人的部署，机器人会以可折叠卡片的形式向你推送二课活动，并且具有一键报名按钮，一般情况下没有必要记忆众多指令的具体用法**

发送 `搜索 xxx` 搜索关键词为xxx的活动

发送 `已报名` 查看已报名的活动，并可一键取消报名

发送 `升级` 升级机器人到最新版本

发送 `扫描` 扫描第二课堂系统，更新数据库（机器人会定时自动扫描，一般无需执行此指令）

[机器人指令的详细文档](./docs/commands.md)


### 4. AI 筛选（可选）

- 可以以自然语言描述个人信息（专业、研究方向、兴趣等），让AI帮你筛选你可能感兴趣的活动
- 支持 OpenAI 兼容的api，你可以接入自己的 Kimi / Qwen / Siliconflow 等平台的api
- AI 判断结果自动存入数据库，避免对同一二课活动重复调用 API
- 支持并发限制和请求速率限制，防止触发 API 限流
- 可以自定义系统提示词和用户提示词，默认情况下无需修改二者

### 5. 数据管理

- **二课数据库**：保留最近 N 次扫描的二课信息数据库（N可配置）
- **用户偏好数据库**：用户的不感兴趣黑名单/感兴趣白名单在本地数据库中永久保存
- **搜索索引**：默认保持标题中文子串搜索；可通过 `search.mode: full_text` 启用 SQLite FTS5 trigram 搜索标题、组织单位、标签、活动构想和地点，环境不支持时会自动回退

### 6. 日历同步

报名成功后，NextArc 可以自动将活动同步到你的飞书日历。

当前仅保留邀请模式：报名成功后，机器人会向你的飞书日历发送日程邀请，接受后即可在日历中查看。
邀请发送后，请在飞书的“日历助手”消息或飞书日历中接受邀请；机器人返回的文本不会再附带事件直链。

要启用该功能，除了在配置文件中开启 `feishu.calendar_sync.enabled`，还需要在飞书应用权限中开通 `calendar:calendar`。
为了让机器人能稳定识别日历邀请接收者，建议同时配置 `feishu.user_id`。

**配置示例**

```yaml
feishu:
  # 首次运行后进入机器人私聊或发送消息，从日志获取 user_id
  user_id: "ou_xxxxxxxxxxxxxxxx"
  # 日历同步配置
  calendar_sync:
    enabled: true
```

关闭后则只执行报名，不再发送日历邀请。

## 快速部署

**非常建议**在我校 [vlab平台](https://vlab.ustc.edu.cn/vm/) 的虚拟机上部署本服务，具有以下优势

- 不花钱，任何学生都可免费申请
- 24H运行，部署好就不用管了
- 校内IP，或许CAS验证时比较稳定

**在部署中遇到任何问题，欢迎加QQ群 1094767572 询问**

【待补充】

[旧版本（无daemon化）部署教程](./docs/deployment_legacy.md) （无需查看此文档）


## 项目结构

```
NextArc/
├── src/                          # 源代码目录
│   ├── main.py                   # 应用入口，NextArcApp 主类
│   ├── cli.py                    # 命令行工具（feishu-register、ai-config、doctor 等）
│   ├── app/                      # 应用上下文与运行时依赖构造
│   │   ├── context.py            # AppContext 单实例运行时依赖入口
│   │   └── factory.py            # 配置构建辅助函数
│   ├── config/                   # 配置管理模块
│   │   ├── settings.py           # 主配置加载与验证
│   │   ├── preferences.py        # 推送偏好配置管理
│   │   └── runtime_state.py      # 运行时状态管理
│   ├── context/                  # 最近展示、搜索结果、确认操作等上下文
│   │   ├── manager.py            # 上下文生命周期管理
│   │   ├── models.py             # 上下文数据模型
│   │   ├── policies.py           # 上下文清理策略
│   │   └── store.py              # 上下文存储实现
│   ├── core/                     # 核心业务逻辑
│   │   ├── scanner.py            # 定时任务生命周期入口
│   │   ├── auth_manager.py       # 认证与会话管理
│   │   ├── db_manager.py         # 数据库文件管理
│   │   ├── secondclass_db.py     # 活动快照写入
│   │   ├── diff_engine.py        # 活动差异对比引擎
│   │   ├── batch_updater.py      # 批量并发更新 SecondClass 实例
│   │   ├── version_checker.py    # 基于 Git 仓库的版本检查
│   │   ├── runtime_maintenance.py# 运行时维护任务
│   │   ├── ai_filter.py          # AI 智能筛选器
│   │   ├── time_filter.py        # 时间冲突筛选器
│   │   ├── overlay_filter.py     # 已报名活动时间重叠筛选器
│   │   ├── enrolled_filter.py    # 已报名活动筛选器
│   │   ├── search_index.py       # SQLite 搜索索引维护
│   │   ├── user_preference_manager.py  # 用户偏好数据库管理
│   │   ├── repositories/         # 活动快照和偏好数据库访问层
│   │   │   ├── activity_repository.py    # 活动快照查询
│   │   │   └── preference_repository.py  # 用户偏好查询
│   │   ├── services/             # 活动查询、深度更新、报名用例服务
│   │   │   ├── activity_query_service.py   # /valid、/search、/info 查询
│   │   │   ├── activity_update_service.py  # 并发深度更新
│   │   │   └── enrollment_service.py       # 报名、取消报名和日历同步
│   │   ├── filtering/            # 统一筛选管线
│   │   │   ├── pipeline.py       # 筛选流程编排
│   │   │   ├── context.py        # 筛选上下文
│   │   │   └── result.py         # 筛选结果模型
│   │   ├── scanning/             # 扫描同步、diff、调度和事件发布编排
│   │   │   ├── coordinator.py    # 扫描协调器
│   │   │   ├── scheduler.py      # 扫描调度器
│   │   │   ├── sync_service.py   # 活动同步服务
│   │   │   ├── diff_service.py   # 差异对比服务
│   │   │   └── result.py         # 扫描结果模型
│   │   └── events/               # 事件系统
│   │       ├── scan_events.py    # 扫描相关事件定义
│   │       └── version_events.py # 版本检查事件定义
│   ├── models/                   # 数据模型
│   │   ├── activity.py           # SecondClass 兼容导出
│   │   ├── secondclass_mapper.py # SecondClass <-> 数据库行转换
│   │   ├── secondclass_view.py   # 展示字段读取和格式化辅助
│   │   ├── diff_result.py        # 差异结果数据模型
│   │   ├── filter_result.py      # 筛选结果数据模型
│   │   └── session.py            # 用户会话模型
│   ├── feishu_bot/               # 飞书机器人模块
│   │   ├── client.py             # 飞书客户端（WebSocket 连接）
│   │   ├── message_router.py     # 消息路由分发
│   │   ├── card_builder.py       # 飞书活动卡片构建
│   │   ├── card_handler.py       # 卡片交互处理器
│   │   ├── calendar_service.py   # 飞书日历同步服务
│   │   └── handlers/             # 指令处理器
│   │       ├── base.py           # 处理器基类
│   │       ├── help.py           # /help 指令
│   │       ├── alive.py          # /alive 指令
│   │       ├── check.py          # /check 指令
│   │       ├── info.py           # /info 指令
│   │       ├── search.py         # /search 指令
│   │       ├── join.py           # /join 指令
│   │       ├── cancel.py         # /cancel 指令
│   │       ├── valid.py          # /valid 指令
│   │       ├── ignore.py         # /ignore 指令
│   │       ├── interested.py     # /interested 指令
│   │       ├── preference.py     # /preference 指令
│   │       ├── upgrade.py        # /upgrade 指令
│   │       ├── menu.py           # 菜单指令
│   │       ├── restart.py        # 重启指令
│   │       └── __init__.py       # 处理器注册
│   ├── notifications/            # 通知服务模块
│   │   ├── builders.py           # 通知文本和卡片请求构建
│   │   ├── service.py            # 通知服务基类
│   │   ├── feishu_service.py     # 飞书通知服务实现
│   │   ├── listener.py           # 事件监听与通知触发
│   │   └── response.py           # 响应数据模型
│   └── utils/                    # 工具函数
│       ├── logger.py             # 日志配置
│       ├── formatter.py          # 文本格式化工具
│       ├── rate_limiter.py       # 速率限制器
│       └── retry.py              # 重试机制
├── config/                       # 配置文件目录
│   ├── config.example.yaml       # 主配置模板
│   ├── config.yaml               # 主配置文件（需复制模板创建）
│   ├── preferences.example.yaml  # 推送偏好配置模板
│   ├── preferences.yaml          # 推送偏好配置（需复制模板创建）
│   └── prompts/                  # AI 提示词文件目录
│       ├── system_prompt.md      # 系统提示词
│       └── user_prompt.md        # 用户提示词
├── deploy/                       # 部署脚本与 systemd 服务文件
│   ├── install-nextarc.sh        # 一键安装脚本
│   ├── upgrade-nextarc.sh        # 一键升级脚本
│   ├── nextarc.service            # systemd 服务配置
│   ├── nextarc-upgrade.service    # 升级服务配置
│   └── nextarc-upgrade.path       # 升级触发 path 配置
├── docs/                         # 文档目录
│   ├── change_log.md             # 更新记录
│   ├── commands.md               # 机器人指令文档
│   ├── deployment_legacy.md      # 旧版部署教程
│   ├── feishu_permissions.json   # 飞书权限配置模板
│   ├── install_and_migration.md  # 安装、迁移与升级文档
│   └── set_another_upsteam.md    # 切换上游仓库文档
├── requirements.txt              # Python 依赖清单
├── README.md                     # 项目说明文档
└── LICENSE.txt                   # GPL-3.0 许可证

```

### 核心组件说明

| 组件                        | 职责                   | 关键类/文件                            |
|---------------------------|----------------------|-----------------------------------|
| **NextArcApp**            | 应用生命周期管理             | `main.py`                         |
| **CLI**                   | 命令行工具入口              | `cli.py`                          |
| **AppContext**            | 单实例运行时依赖入口           | `app/context.py`                  |
| **Factory Functions**     | 配置构建辅助函数             | `app/factory.py`                  |
| **ActivityScanner**       | 定时任务生命周期             | `core/scanner.py`                 |
| **VersionScheduler**      | 版本检查定时调度           | `core/scanning/scheduler.py`      |
| **SyncService**           | 活动同步服务               | `core/scanning/sync_service.py`   |
| **DiffService**           | 差异对比服务               | `core/scanning/diff_service.py`   |
| **ScanCoordinator**       | 扫描同步、diff、筛选和事件发布   | `core/scanning/coordinator.py`    |
| **SecondClassBatchUpdater** | 批量并发更新 SecondClass 实例 | `core/batch_updater.py`           |
| **VersionChecker**        | 基于 Git 仓库的版本检查       | `core/version_checker.py`         |
| **ActivityRepository**    | 活动快照数据库只读查询          | `core/repositories/activity_repository.py` |
| **PreferenceRepository**  | 用户偏好数据库查询            | `core/repositories/preference_repository.py` |
| **ActivityQueryService**  | `/valid`、`/search`、`/info` 查询用例 | `core/services/activity_query_service.py` |
| **ActivityUpdateService** | 并发深度更新活动信息           | `core/services/activity_update_service.py` |
| **EnrollmentService**     | 报名、取消报名和日历同步         | `core/services/enrollment_service.py` |
| **ActivityFilterPipeline**| 统一 `/valid` 和通知筛选流程    | `core/filtering/pipeline.py`      |
| **SearchIndex Functions** | 活动快照基础索引和 FTS5 trigram 搜索索引维护 | `core/search_index.py`            |
| **ContextManager**        | 搜索结果、最近展示和确认状态      | `context/manager.py`              |
| **AIFilter**              | AI 智能筛选、结果缓存         | `core/ai_filter.py`               |
| **TimeFilter**            | 时间冲突检测、多模式筛选         | `core/time_filter.py`             |
| **FeishuBot**             | 飞书 WebSocket 连接、消息接收 | `feishu_bot/client.py`            |
| **MessageRouter**         | 指令路由分发               | `feishu_bot/message_router.py`    |
| **CalendarService**       | 飞书日历同步服务             | `feishu_bot/calendar_service.py`  |
| **NotificationListener**  | 事件监听、通知发送            | `notifications/listener.py`       |
| **UserPreferenceManager** | 用户偏好持久化              | `core/user_preference_manager.py` |

## TODO

- [ ] 推送系列活动新增子活动
- [ ] 添加愿望单功能，如果出现空闲报名名额，自动报名
- [ ] 隐藏无效的飞书卡片按钮
- [ ] 优化数据库设计
- [ ] 按钮内容在线更新
- [ ] 以非侵入式形态显示二课详情（暂时无法实现）

## 联系我

QQ群 1094767572

## 致谢

感谢 [pyustc](https://github.com/USTC-XeF2/pyustc) 库

## License

GPL-3.0
