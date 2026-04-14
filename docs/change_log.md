# 版本变更说明

## v2.0.0

2020-04-14

推荐使用环境变量的方式配置用户名和密码，提升应用安全性

迁移方法：

1. 关闭原先的 NextArc 程序
2. 在原先config.yaml文件中删除你的学号和密码
3. 将配置文件中的 `auth_mode` 从 `file` 改为 `env`
4. 在你准备用于启动 NextArc 的 shell 中输入 `export USTC_USERNAME = "PB24123456"`（你的学号） ，然后输入 `export USTC_PASSWORD = "qwerty1234"`（你的密码）
5. 在这个 shell 中启动 NextArc

注意：如果关闭了这个设置过环境变量的 shell ，需要在新 shell 中重新设置以上环境变量，然后才能启动程序
