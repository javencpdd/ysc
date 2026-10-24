# 部署到另一台 M20 —— 已迁移

> **本文内容已并入 [note/移植部署流程.md](../note/移植部署流程.md)，此处只保留跳转。**
>
> 为什么移走：`pack.sh` **只打包 `note/`，不打包 `docs/`** —— 文档放在 `note/`
> 才会随部署包上机，在 AOS 上排障时能直接看；放 `docs/` 只有 PC 侧可见。
>
> 迁移日期：2026-10-18。**请不要往本文件加内容**，避免两份漂移。

## 去这里

| 你要找什么 | 位置 |
|---|---|
| 换机要复制什么、路径有什么要求 | [note/移植部署流程.md](../note/移植部署流程.md) §1–§3 |
| 完整步骤（首次 / 迭代 / 非默认路径） | 同上 §4 |
| 验收与回滚 | 同上 §5–§6 |
| 常见坑对照表 | 同上 §7 |
| 换机前必须核对的三件事 | 同上 §9 |
| 机器特定项（sudoers 用户名、relay 目标、热点密码…） | 同上 §3 |

## 相关

- 同机部署 / 升级：[deployment.md](deployment.md)
- 只读预检脚本：[tools/preflight_new_host.sh](../tools/preflight_new_host.sh)
- 受控提权 helper 安装器：[deploy/install_helpers.sh](../deploy/install_helpers.sh)
