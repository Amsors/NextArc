# 使用lug维护的校内git服务作为上游更新仓库



在项目**根目录**下执行

```bash
git remote add gitlab_lug https://git.lug.ustc.edu.cn/amsors/nextarc_mirror
```

此条命令的作用是，添加一个名为`gitlab_lug`的远程仓库，指向 `https://git.lug.ustc.edu.cn/amsors/nextarc_mirror`（由我校 linux user group 维护，无需科学上网即可访问）

然后，在 `config.yaml` 中，将 `version_check:remote_name` 改为 `"gitlab_lug"`

最后，重启当前运行的机器人（记得先关掉之前的机器人，并记得还在虚拟环境中运行）