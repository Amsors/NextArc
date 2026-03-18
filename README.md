# NextArc - 第二课堂活动监控机器人

自动监控 USTC 第二课堂活动变化，支持飞书机器人交互。



## ⚠️ 环境要求

**请在隔离的 conda 环境中运行**

本项目依赖 `pyustc` 库，建议在隔离的 conda 环境中安装此库，然后再运行机器人。



## 安装

### 1. 确保已安装 pyustc

```bash
conda activate [your_conda_env]
python -c "import pyustc; print('pyustc 已安装')"
```

### 2. 安装项目依赖

```bash
# 在 pyustc 环境中安装
cd [path_to_NextArc]
pip install -r requirements.txt
```

### 3. 配置

复制配置文件模板并填写：

```bash
cp src/config/config.example.yaml src/config/config.yaml
# 然后，编辑 config.yaml 填写你的账号和飞书凭证
```

### 配置说明

见 `config.yaml` 中的注释



## 运行

```bash
# 确保在已经安装 pyustc 的环境中
conda activate [your_conda_env]

# 运行主程序
python src/main.py
```



## 功能说明

### 定时扫描
- 每15分钟自动扫描一次可报名的第二课堂活动
- 创建带时间戳的数据库文件保存数据
- 自动保留最近10份历史数据库

### 自动通知
- 当用户已报名的活动信息发生变化时，自动推送通知

### 飞书机器人指令

| 指令 | 功能 |
|------|------|
| `/update` | 手动更新数据库 |
| `/check` | 更新并显示与上次扫描的差异 |
| `/info` | 显示已报名的所有活动 |
| `/cancel 序号` | 取消报名（需二次确认） |
| `/search 关键词` | 搜索活动 |
| `/join 序号` | 报名搜索结果的活动（需二次确认） |
| `/alive` | 检查服务状态 |
| `/help` | 获取帮助信息 |



## 项目结构

```
NextArc/
├── src/
│   ├── config/         # 配置管理
│   ├── core/           # 核心功能（扫描、对比、认证）
│   ├── models/         # 数据模型
│   ├── utils/          # 工具函数
│   └── main.py         # 程序入口
├── data/               # 数据库文件（自动创建）
├── dev_docs/           # 开发文档
├── requirements.txt    # 依赖列表
└── README.md
```



## 致谢

感谢 [pyustc](https://https://github.com/USTC-XeF2/pyustc) 库，解析了学校相关api接口，在此表示感谢



## License

GPL-3.0
