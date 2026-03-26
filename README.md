# NextArc - 第二课堂活动监控机器人

自动监控 USTC 第二课堂活动变化，支持飞书机器人交互。

## 项目介绍

待补充

## 功能说明

待补充

## 快速部署

**非常建议**在我校 [vlab平台](https://vlab.ustc.edu.cn/vm/) 申请的虚拟机上部署本服务，具有以下优势

- 不花钱
- 24H运行，部署好就不用管了
- 校内IP，或许CAS验证时比较稳定

### 1. 拉取项目代码并安装 pyustc 库

#### 1.1 拉取仓库代码

```bash
# 在你想要存放 NextArc 代码的地方
git clone https://github.com/Amsors/NextArc
```

#### 1.2 拉取 pyustc 库代码

本项目依赖 pyustc 库调取学校相关api，本人fork后开发了数据库相关功能，但是尚未合并到上游仓库，目前请调用我的 pyustc 仓库

```bash
# 在你想要存放 pyustc 代码的地方
git clone https://github.com/Amsors/pyustc
```

⚠️切换到数据库开发分支

```bash
# 在 pyustc 库安装的根目录下
git switch feat/database
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



## 项目结构

待补充



## 致谢

感谢 [pyustc](https://github.com/USTC-XeF2/pyustc) 库，解析了学校相关api接口，在此表示感谢



## License

GPL-3.0
