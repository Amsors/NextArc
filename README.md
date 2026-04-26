# NextArc - 第二课堂活动监控机器人

自动监控 USTC 第二课堂活动变化，支持飞书机器人交互。

## 重要更新日志

[请查看文档](./docs/change_log.md)

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

你的姓名、学号、密码等信息都不会上传到除了我校CAS认证(`id.ustc.edu.cn`)、二课系统(`young.ustc.edu.cn`)
以外的任何服务器上，机器人本身不会以任何形式收集任何信息。推送消息只会通过飞书SDK，经飞书的服务器推送给你，不经过开发者或其他任何第三方，无需担心隐私泄露

## 风险提示
**请保证部署机器人的服务器完全由你控制，如因写有账号密码的配置文件泄露，你的服务器被入侵等原因导致账号密码或其他隐私信息泄露，开发者不对任何后果承担任何负责**

请对你的服务器采取包括但不限于以下安全措施：

- 配置使用证书的ssh登录
- 修改默认ssh端口号，安装fail2ban等软件防止爆破
- 只允许特定ip通过ssh连接
- 定期更新系统包

欢迎对本项目和 pyustc 项目进行安全审计


## 功能说明

### 1. 自动活动扫描

- **定时扫描**：可配置扫描间隔（默认 15 分钟），自动检测第二课堂活动变化，获取的数据库记录在本地SQLite数据库中
- **差异对比**：自动对比新旧数据库，识别新增、修改、删除的活动
- **深度更新**：可一键深度更新当前所有二课的信息，包括信息报名人数等信息

### 2. 推送筛选

NextArc提供多样的筛选机制，确保只推送你可能会参与的活动：

| 筛选类型            | 说明                                                   | 优先级 |
|-------------------|------------------------------------------------------|-----|
| **感兴趣白名单**     | 标记为感兴趣的活动，绕过不感兴趣、重叠、时间和 AI 等用户侧筛选；不绕过不可报名、已报名等硬约束 | 最高  |
| **已报名筛选**       | 自动过滤已报名的活动，避免重复通知                                 | 高   |
| **不感兴趣黑名单**   | 标记为"不感兴趣"的活动，后续不再推送                              | 中   |
| **已有活动重叠筛选** | 检测待筛选的单次活动是否与已报名活动时间重叠；系列活动不参与此筛选      | 中   |
| **时间筛选**         | 根据用户配置的没空时间段，过滤时间冲突的活动                         | 中   |
| **AI 智能筛选**      | 基于大语言模型分析活动内容和用户偏好，推断是否感兴趣                 | 低   |

感兴趣白名单和不感兴趣黑名单均存储在本地数据库中，白名单的预期用途是强制绕过用户侧筛选因素，而非类似“Steam愿望单”的机制；它不会让已报名或不可报名活动重新进入推荐列表（例如，配置了周三下午16:
00至18:
00没空，但某个周三的一次保研经验分享二课你非常感兴趣，可以将此二课加入白名单，避免此活动因为时间重叠被筛选掉；又例如，你在发给大模型的提示词中写到“我对一切音乐相关二课不感兴趣”，但你对某一次音乐会二课感兴趣，可以将此二课加入白名单，避免此活动被AI判定为不感兴趣）

时间筛选有以下三种配置方式：

- `partial`（部分重叠）：活动时间与用户非空闲时间有任何交集，即过滤此二课（适合固定课程）
- `full`（完全包含）：活动时间完全落在非空闲时间段内，才过滤此二课
- `threshold`（比例阈值）：重叠时间占活动时长比例超过阈值，才过滤此二课

### 3. 飞书机器人交互

**只要完成机器人的部署，机器人会以可折叠卡片的形式向你推送二课活动，并且具有一键报名按钮，一般情况下没有必要记忆以下众多指令，此模块内容无需阅读**

省流：

发送`搜索 xxx`搜索关键词为xxx的活动

发送`已报名`查看已报名的活动，并可一键取消报名

发送`升级`升级机器人到最新版本

发送`扫描`扫描第二课堂系统，更新数据库

其他指令太长不看...不想看的可以跳过下述说明

全部指令如下：

| 指令                      | 别名              | 功能说明          | 示例                 |
|-------------------------|-----------------|---------------|--------------------|
| `/help`                 | 帮助 ？ ?          | 显示帮助信息        | `/help`            |
| `/alive`                | 系统状态 状态...      | 查看系统运行状态      | `/alive`           |
| `/check`                | 更新 检查 差异 扫描 ... | 更新数据库并检查差异    | `/check`           |
| `/valid`                | 可报名 可报名活动       | 查看当前可报名的活动列表  | `/valid`           |
| `/info`                 | 已经报名 已报名        | 查看已报名的活动详情    | `/info`            |
| `/search <关键词>`         | 搜索 查找           | 搜索第二课堂活动      | `/search 讲座`       |
| `/join <序号>`            | 报名 参加 参与        | 报名指定活动        | `/join 1`          |
| `/cancel <序号>`          | 取消报名 取消         | 取消报名指定活动      | `/cancel 1`        |
| `/ignore <序号>`          | 不感兴趣 忽略         | 将活动标记为"不感兴趣"  | `/ignore 2`        |
| `/interested <类型> <序号>` | 感兴趣             | 将被筛选的活动标记为感兴趣 | `/interested ai 1` |
| `/upgrade`              | 升级 更新程序         | 从 git 拉取更新并重启 | `/upgrade`         |
| `/preference [类型]`   | 偏好 愿望单          | 查看偏好库与当前活动库交集中的活动  | `/preference 感兴趣` |

指令可以完全被别名替代，例如 `/search 英语` 指令的行为和 `搜索 英语` 完全相同

完全可以仅使用中文指令，不使用任何英文指令

**二级指令说明**

部分指令支持二级功能，通过在主指令后添加参数实现：

**`/check` 指令：**

| 二级指令   | 说明            | 示例            |
|--------|---------------|---------------|
| `深度`   | 深度更新活动信息      | `/check 深度`   |
| `推送`   | 更新后推送新活动和报名变化 | `/check 推送`   |
| `对比差异` | 推送详细的差异对比信息   | `/check 对比差异` |

可同时组合使用任意个`/check`指令的二级指令，如`检查 深度 推送`

**`/valid` 指令：**

| 二级指令   | 说明                     | 示例            |
|--------|------------------------|---------------|
| `重新扫描` | 先更新数据库再查询              | `/valid 重新扫描` |
| `全部`   | 显示当前可报名状态下的所有活动（跳过已报名、不感兴趣、重叠、时间、AI 等筛选） | `/valid 全部`   |
| `深度`   | 深度更新活动信息               | `/valid 深度`   |
| `重新筛选` | 重新进行AI筛选（不使用缓存）        | `/valid 重新筛选` |

可同时组合使用任意个`/valid`指令的二级指令，如`可报名 全部 深度`

**`/info` 指令：**

| 二级指令                                        | 说明                                                         | 示例           |
| ----------------------------------------------- | ------------------------------------------------------------ | -------------- |
| `结项` / `已经结项` / `已结项` / `end`          | 显示结项和异常结项的所有活动                                 | `/info 结项`   |
| `即将结项` / `未结项` / `尚未结项`  / `pending` | 显示公示/追加公示中、公示结束、学时申请中、学时审核通过、学时驳回的活动 | `/info 未结项` |
| `异常` / `abnormal`                             | 显示学时驳回的活动                                           | `/info 异常`   |

对`/info`，只能携带最多一个二级指令，如不携带二级指令，则仅显示发布、报名中、报名已结束的活动

**`/ignore` 指令：**

| 参数格式   | 说明                  | 示例                                            |
|--------|---------------------|-----------------------------------------------|
| `<序号>` | 指定序号，支持单个、多个或范围     | `/ignore 1` / `/ignore 1,2,3` / `/ignore 1-5` |
| `全部`   | 忽略所有上次显示的活动         | `/ignore 全部`                                  |
| `AI`   | 添加AI筛选掉的所有活动到不感兴趣列表 | `/ignore AI`                                  |

对`/ignore`，必须提供以上三种参数的其中一种

目前已加入一键不感兴趣按钮，点击即可将活动加入不感兴趣列表，一般情况下，无需该指令

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
若未配置 `user_id`，程序会在你首次进入机器人私聊或发送消息时，在控制台打印当前 `user_id`，可复制到 `config.yaml` 后长期使用。

**`/upgrade` 指令：**

执行后自动检查 git 远程仓库是否有新版本：

- 如果有更新，会显示变更日志并询问是否确认更新
- 用户确认后执行 `git pull`，成功后自动重启应用
- 如果更新失败（网络错误、代码冲突等），会提示错误信息，不会重启

**`/interested` 指令：**

| 参数       | 说明                                                                       | 示例                                           |
|----------|--------------------------------------------------------------------------|----------------------------------------------|
| `<筛选类型>` | `ai` - AI筛选掉的活动<br>`时间`/`time` - 时间筛选掉的活动<br>`重叠`/`overlay` - 时间重叠筛选掉的活动<br>`忽略`/`数据库`/`db` - 数据库筛选掉的活动 | `/interested ai 1`                           |
| `<序号>`   | 指定序号，支持单个、多个、范围或全部                                                       | `/interested ai 1,2,3` / `/interested 时间 全部` |

对`/interested`，必须提供以上两个参数

当飞书定时扫描过后，或使用`/valid`或`/check 推送`
命令后，飞书机器人会向你发送经过筛选的二课信息，二课信息以折叠卡片的形式展示，你可以点击不感兴趣按钮将此二课加入黑名单，也可以点击报名按钮一键报名（仅对于单次活动有效）

**`/preference` 指令：**

- 显示的是“感兴趣/不感兴趣数据库”与“当前最新活动数据库”的交集
- 如果某个历史活动已不在当前活动库中，则不会出现在 `/preference` 结果里
- 支持 `/preference`、`/preference 感兴趣`、`/preference 不感兴趣`

### 4. AI 筛选（可选）

- 可以以自然语言描述个人信息（专业、研究方向、兴趣等），让AI帮你筛选你可能感兴趣的活动
- 支持 OpenAI 兼容的api，你可以接入自己的 Kimi / Qwen / Siliconflow 等平台的api
- AI 判断结果自动存入数据库，避免对同一二课活动重复调用 API
- 支持并发限制和请求速率限制，防止触发 API 限流
- 可以自定义系统提示词和用户提示词，默认情况下无需修改二者，仅修改配置文件中的个人信息即可

### 5. 数据管理

- **二课数据库**：保留最近 N 次扫描的二课信息数据库（N可配置）
- **用户偏好数据库**：用户的不感兴趣黑名单/感兴趣白名单在本地数据库中永久保存
- **搜索索引**：默认保持标题中文子串搜索；可通过 `search.mode: full_text` 启用 SQLite FTS5 trigram 搜索标题、组织单位、标签、活动构想和地点，环境不支持时会自动回退

## 快速部署

**非常建议**在我校 [vlab平台](https://vlab.ustc.edu.cn/vm/) 的虚拟机上部署本服务，具有以下优势

- 不花钱，任何学生都可免费申请
- 24H运行，部署好就不用管了
- 校内IP，或许CAS验证时比较稳定

**在部署中遇到任何问题，欢迎加QQ群 1094767572 询问**

你部署的服务器必须24H运行，否则会导致服务中断，如果使用学校的vlab部署，请安装`screen`等软件(`sudo apt install screen`)
，在虚拟screen session中运行软件，避免关闭ssh连接后进程被杀死（本项目尚不支持服务化部署）

本机器人不需要公网ip

**请保证部署机器人的服务器完全由你控制，如因写有账号密码的配置文件泄露，服务器被入侵等原因导致个人信息泄露，开发者不负责**

### 1. 拉取项目代码并安装 pyustc 库

#### 1.1 拉取仓库代码

```bash
# 在你想要存放 NextArc 代码的地方
git clone https://github.com/Amsors/NextArc
```

#### 1.2 拉取 pyustc 库代码

本项目依赖 pyustc 库调取学校相关api，本人fork后开发了数据库相关功能，但是尚未合并到上游仓库，**目前请使用我的 pyustc 仓库**

```bash
# 在你想要存放 pyustc 代码的地方
git clone https://github.com/Amsors/pyustc
```

⚠️**切换到NextArc适配分支**

```bash
# 在 pyustc 库安装的根目录下
git switch adapt/NextArc
```

#### 1.3 创建环境并安装依赖

⚠️请务必在**隔离的虚拟环境中**安装 pyustc 和运行此项目

```bash
# 假设你使用的是 conda...
conda create -n [your_cond_env_name]
conda activate [your_conda_env_name]
```

快速部署的以下部分默认在虚拟环境中运行

```bash
cd /path/to/pyustc/ # 打开 pyustc 库的根目录
pip install -e .
```

如果出现`PEP 668`相关的警告，如环境被pyenv劫持，使用了`~/.pyenv`中的pip，请自行搜索解决方案

通过以下命令检查安装

```bash
python -c "import pyustc; print('pyustc 已安装')" 
```

如果输出了 `pyustc 已安装` 则表示已经 pyustc 已经安装成功

然后安装本项目的依赖

```bash
cd /path/to/NextArc/ # 打开 NextArc 项目的根目录
pip install -r requirements.txt
```

### 2. 配置

#### 2.1 本项目配置

##### 2.1.1 项目配置（必须填写）

复制配置文件模板并填写：

```bash
cp config/config.example.yaml config/config.yaml
# 然后，编辑 config/config.yaml 填写相关配置信息
```

具体配置方式见 `config/config.yaml` 中的说明

##### 2.1.2 推送偏好配置（可选）

如需启用时间筛选功能，复制并配置推送偏好文件：

```bash
cp config/preferences.example.yaml config/preferences.yaml
# 编辑 config/preferences.yaml 配置时间偏好
```

具体配置方式见 `config/preferences.yaml` 中的说明

#### 2.2 飞书配置

##### 2.2.1 在飞书平台创建应用

登录[飞书开放平台的开发者后台](https://open.feishu.cn/app)

点击 `创建企业应用`

填写应用名称和描述，然后创建应用

`添加应用能力`  -> 点击 `机器人` 下方的 `添加`

复制项目 `./docs/feishu_permissions.json` 文件的全文

点击左侧 `权限管理` -> `批量导入/导出权限` -> `导入` ，将其中的示例权限配置删除，替换为刚才复制的文本 ->
`下一步，确认新增权限` -> `申请开通` -> `确认`

其中已包含日历同步所需的 `calendar:calendar` 权限；如果你不需要报名后自动发送飞书日程邀请，也可以关闭 `config.yaml` 中的 `feishu.calendar_sync.enabled`

点击左侧 `事件与回调` -> `事件配置` -> `订阅方式` -> 选择 `使用长连接接收事件`，保存

点击 `添加事件` ，搜索并添加以下三个权限：`im.chat.access_event.bot_p2p_chat_entered_v1` `im.message.message_read_v1`
`im.message.receive_v1`

点击 `事件配置` 旁边的 `回调配置` -> `添加回调` ，搜索并添加以下权限：`card.action.trigger`

点击左侧 `凭证与基础信息` ，复制 `App ID` 和 `App secret` 到项目的 `./config/config.yaml` 配置文件中

点击左侧 `版本管理与发布` -> `创建版本` -> 填写信息，发布版本

### 3. 运行

```bash
# 运行主程序
python src/main.py
```

启动程序后，当你看到stdout输出`[INFO] connected to wss://msg-frontier.feishu.cn/ws/v2?`
相关字样后，请在飞书app搜索你创建机器人时机器人的名字，然后向这个机器人随便发一句话，然后程序会输出
`...当前 chat_id: oc_xxxxxxxxxxxx ...`，请将`oc_xxxxxxxxxxxx`这一部分复制下来，配置在`config.yaml`配置文件中

然后，请退出飞书（推荐清理后台，彻底杀掉飞书），然后重启NextArc，等待10s后进入飞书，你应该可以收到飞书机器人**主动**向你发送的问候消息

看到问候消息表明配置完成了

## 项目结构

```
NextArc/
├── src/                          # 源代码目录
│   ├── main.py                   # 应用入口，NextArcApp 主类
│   ├── app/                      # AppContext 与运行时依赖构造辅助
│   ├── config/                   # 配置管理模块
│   │   ├── settings.py           # 主配置加载与验证
│   │   └── preferences.py        # 推送偏好配置管理
│   ├── context/                  # 最近展示、搜索结果、确认操作等上下文
│   ├── core/                     # 核心业务逻辑
│   │   ├── scanner.py            # 定时任务生命周期入口
│   │   ├── auth_manager.py       # 认证与会话管理
│   │   ├── db_manager.py         # 数据库文件管理
│   │   ├── secondclass_db.py     # 活动快照写入
│   │   ├── diff_engine.py        # 活动差异对比引擎
│   │   ├── ai_filter.py          # AI 智能筛选器
│   │   ├── time_filter.py        # 时间冲突筛选器
│   │   ├── overlay_filter.py     # 已报名活动时间重叠筛选器
│   │   ├── enrolled_filter.py    # 已报名活动筛选器
│   │   ├── search_index.py       # SQLite 搜索索引维护
│   │   ├── user_preference_manager.py  # 用户偏好数据库管理
│   │   ├── repositories/         # 活动快照和偏好数据库访问层
│   │   ├── services/             # 活动查询、深度更新、报名用例服务
│   │   ├── filtering/            # 统一筛选管线
│   │   ├── scanning/             # 扫描同步、diff、调度和事件发布编排
│   │   └── events/               # 事件系统
│   │       └── scan_events.py    # 扫描相关事件定义
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
│   │       ├── upgrade.py        # /upgrade 指令
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
├── data/                         # 默认数据存储目录
│   ├── *.db                      # 活动数据库（按时间戳）
│   └── user_preference.db        # 用户偏好数据库
├── docs/                         # 文档目录
│   └── feishu_permissions.json   # 飞书权限配置模板
├── requirements.txt              # Python 依赖清单
├── README.md                     # 项目说明文档
└── LICENSE.txt                   # GPL-3.0 许可证

```

### 核心组件说明

| 组件                        | 职责                   | 关键类/文件                            |
|---------------------------|----------------------|-----------------------------------|
| **NextArcApp**            | 应用生命周期管理             | `main.py`                         |
| **AppContext**            | 单实例运行时依赖入口           | `app/context.py`                  |
| **ActivityScanner**       | 定时任务生命周期             | `core/scanner.py`                 |
| **ScanCoordinator**       | 扫描同步、diff、筛选和事件发布   | `core/scanning/coordinator.py`    |
| **ActivityRepository**    | 活动快照数据库只读查询          | `core/repositories/activity_repository.py` |
| **ActivityQueryService**  | `/valid`、`/search`、`/info` 查询用例 | `core/services/activity_query_service.py` |
| **ActivityUpdateService** | 并发深度更新活动信息           | `core/services/activity_update_service.py` |
| **EnrollmentService**     | 报名、取消报名和日历同步         | `core/services/enrollment_service.py` |
| **ActivityFilterPipeline**| 统一 `/valid` 和通知筛选流程    | `core/filtering/pipeline.py`      |
| **SearchIndex**           | 活动快照基础索引和 FTS5 trigram 搜索索引维护 | `core/search_index.py`            |
| **ContextManager**        | 搜索结果、最近展示和确认状态      | `context/manager.py`              |
| **AIFilter**              | AI 智能筛选、结果缓存         | `core/ai_filter.py`               |
| **TimeFilter**            | 时间冲突检测、多模式筛选         | `core/time_filter.py`             |
| **FeishuBot**             | 飞书 WebSocket 连接、消息接收 | `feishu_bot/client.py`            |
| **MessageRouter**         | 指令路由分发               | `feishu_bot/message_router.py`    |
| **NotificationListener**  | 事件监听、通知发送            | `notifications/listener.py`       |
| **UserPreferenceManager** | 用户偏好持久化              | `core/user_preference_manager.py` |

### 开发扩展流程

**新增指令**

1. 在 `src/feishu_bot/handlers/` 新建处理器，继承 `CommandHandler`，通过构造函数接收 `AppContext`。
2. handler 只负责参数解析和 `Response` 组装；运行时依赖从 `AppContext` 获取，不新增 classmethod/setter 注入入口。
3. 需要最近展示活动、搜索结果或确认状态时，使用 `ContextManager`。
4. 需要活动查询时，使用 `ActivityQueryService`；需要底层快照读取时，使用 `ActivityRepository`。
5. 需要筛选时，调用 `ActivityFilterPipeline`，避免复制 `/valid` 或扫描通知中的筛选顺序。
6. 需要报名、取消报名或报名后的日历同步时，使用 `EnrollmentService`。
7. 在 `src/feishu_bot/handlers/__init__.py` 注册指令和中文别名，并补充不依赖真实 USTC/飞书的测试。

**新增筛选器**

1. 在统一筛选管线中添加新的 step，必要时把独立判断逻辑放到 `src/core/` 的小筛选器类。
2. step 返回统一的保留活动列表和 `FilteredActivity`，并补充筛选摘要或原因。
3. 新筛选逻辑必须同时服务 `/valid` 与新活动通知，不在入口处复制两套流程。
4. 如需数据库输入，通过 `ActivityRepository` 获取。
5. 补充不依赖真实 USTC/飞书的单元测试。

## TODO

- [ ] 推送系列活动新增子活动
- [ ] 扫描时将子活动加入数据库
- [ ] 添加愿望单功能，如果出现空闲报名名额，自动报名
- [ ] 隐藏无效的飞书卡片按钮
- [ ] 优化数据库设计
- [ ] 按钮内容在线更新（重构后实现）
- [ ] 以非侵入式形态显示二课详情（暂时无法实现）

## 联系我

QQ群 1094767572



## 致谢

感谢 [pyustc](https://github.com/USTC-XeF2/pyustc) 库



## License

GPL-3.0
