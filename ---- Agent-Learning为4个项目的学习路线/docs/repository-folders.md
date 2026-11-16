# 项目文件夹使用说明

打开 [Agent-Learning 的 repos/](../repos/)，可以一起浏览携程助手、RAG、Text2SQL 和 ERP_OPENCLAW。它们通过 Git 子模块关联到总仓库：本地下载后表现为四个项目目录，在 GitHub 点击目录则进入对应原仓库的固定提交。

每个项目仍保留自己的提交历史、章节标签和独立地址。总仓库记录每个项目选用的版本，便于复现同一套学习环境；它不会自动追随各项目上游的最新提交。这是 Git 子模块的标准行为，详见 [Git 子模块说明](https://git-scm.com/docs/gitsubmodules)。

## 首次下载全部项目

先安装 Git 和 Python 3.11+：

```sh
git clone --recurse-submodules https://github.com/ooo1208/Agent-Learning.git
cd Agent-Learning
python learn.py verify
```

`--recurse-submodules` 会将四个项目一起下载到 `repos/`。验证默认运行三个教学项目的离线检查；ERP 服务安装和运行仍需遵循其 README。递归克隆不会安装 Java、数据库、模型服务或其他 ERP 依赖。

GitHub 的普通 ZIP 下载不包含子模块源码。若需要完整学习工程，使用递归克隆命令。

## 已经普通克隆过总仓库

进入现有的 `Agent-Learning` 目录，可以继续使用原来的下载入口：

```sh
python learn.py clone
```

它只下载或初始化携程助手、RAG、Text2SQL 三个教学项目。需要全部四个项目时执行：

```sh
python learn.py clone --with-erp
```

脚本保留已有项目和修改；如果当前版本不符合总仓库的记录，按输出提示处理，不会强行覆盖学习代码。

## 更新已下载的项目

先保存总仓库和各子项目中的修改。准备自己写代码时，先在相应子项目中新建学习分支，再修改并提交，避免切换固定版本时遗漏个人工作。子模块初始化后通常处于固定提交，而非某个开发分支。

在总仓库目录执行：

```sh
git pull --ff-only
git submodule update --init --recursive
```

第一条命令取得总入口的更新，第二条将项目目录更新到总入口记录的版本。不要加 `--force`；如果 Git 提示本地修改或分支冲突，先保存和处理自己的工作。命令含义见 [git submodule 官方文档](https://git-scm.com/docs/git-submodule)。

## 修改子项目并发布

先进入对应项目，在自己的分支完成修改、验证、提交并推送。随后回到总仓库，更新该项目的引用及相应版本记录，再提交、推送总仓库。这样别人从总入口下载时，能够取得已经公开的子项目版本。

若只想学习已有章节，可以按各项目 README 中的 `chapter-NN` 标签查看历史版本；本次整理没有重写原有章节或新增虚构章节。

## 目录关联与业务整合

这个文件夹把学习工程和版本组织在一起。Text2SQL 接入 ERP 数据工具、RAG 接入采购知识查询，仍属于 [学习路线](learning-path.md) 中的后续整合任务；统一目录并不代表这些接口已经连接完成。
