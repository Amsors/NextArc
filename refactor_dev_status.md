# Refactor Dev Status

## 已完成范围

按 `refactor_guide.md` 完成阶段 1、2、3 的主要重构。

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

## 验证

- `conda run -n pyustc python -m compileall src tests` 通过。
- `env PYTHONDONTWRITEBYTECODE=1 /home/amsors/anaconda3/envs/pyustc/bin/python -m unittest discover -s tests -v` 通过，5 个测试全绿。
- `git diff --check` 通过。

## 注意

- 沙箱内运行 `aiosqlite` 相关测试会卡住，最终单测是在沙箱外执行通过的。
- 未手动触发真实 USTC/飞书链路。
