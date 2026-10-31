# 蛋解老板 IP 工作台

独立迭代的私有源码仓库。以学员通用版 1.0.0 为起点，保留蛋蛋的方法框架与原生交互，不包含任何人的业务资料、账号、密钥、Cookie、历史稿件或运行数据库。

界面：蛋解方法 → 选题脚本 → 灵感 → 发布 → 数据复盘 → 设置。WorkBuddy负责读本人的资料、调用原版方法、生成与回填；网页负责查看卡片、选择题目、修改和保存。初稿及模拟数据不替本人确认，不自动发布或投流。

脚本确认后，选题脚本页可以把这一版交给本机 StoryCue 访谈，或下载脚本兜底。设置里的「访谈（StoryCue）」分步连接桌面 AI、豆包语音控制台 Key 和追问文字模型；Key 只转发到 StoryCue 的 `.env.local`，不进工作台数据库。StoryCue 页面在 127.0.0.1:3066。它的语音中继默认已是 8866；工作台启动它时仍显式带 `VOICE_RELAY_PORT=8866`，避免和本工作台 8766 冲突。选题编号只能是字母、数字、下划线和连字符。脚本超过 10 万字不会整篇送过去，背景仍压到 1200 字。访谈问答回到该选题。工作台不剪视频，也不接 sayFrame。成片在外部剪好后，到发布页上传，再由学员输入「确认发布」。

## 源码位置

| 路径 | 内容 |
|---|---|
| `assets/workbench/src/` | React界面、样式与交互 |
| `assets/workbench/*.py` | FastAPI、本地资料、方法回填、写稿与复盘逻辑 |
| `assets/frameworks.zip` | 12项原版冻结框架、09兼容副本、原13总装与其原包 |
| `assets/workbench/vendor/` | 独立发布与数据模块的源码及许可 |
| `SKILL.md`、`references/` | WorkBuddy入口与操作流程 |
| `AGENTS.md` | Codex入口；与WorkBuddy共用同一条作业接回、选题和写稿 |
| `scripts/` | 本地开发、便携启动、依赖准备与业务初始化 |

框架ZIP是课程原件，不是使用后备份。展开的框架目录不重复纳入Git；需要修改方法时应单独保存新版本与来源，不覆盖原冻结包。不要把学员的data文件夹或已登录浏览器目录提交到这个仓库。

## 本地开发

需要Python 3.12，以及用于前端构建的Node 22或更新版本。

```sh
python -m venv .venv
# Windows使用 .venv/Scripts/python.exe；Mac使用 .venv/bin/python
python -m pip install -r requirements-dev.txt
python scripts/dev.py prepare
cd assets/workbench
npm ci
npm run build
cd ../..
python scripts/dev.py serve
```

以上`python`需使用刚创建的虚拟环境；不必激活时也可直接写完整解释器路径。默认入口是 http://127.0.0.1:8766 ，可用 `python scripts/dev.py serve --port 18866` 为另一副本选择独立端口；不会停止已有服务。数据只写当前仓库的 `assets/workbench/data`，默认空白。

开发界面时，在 `assets/workbench` 运行 `npm run dev`，另一个终端运行后端；Vite将 `/api` 转发给本机8766。首次业务可让WorkBuddy读取本仓库SKILL.md后，通过 `scripts/student_profile.py` 初始化本人的业务；不要从其他人的数据库复制。

## 检查

```sh
python scripts/dev.py test
node --test assets/workbench/tests/*.test.mjs
```

测试使用临时目录和明确虚构的独立输入，不需要真实账号或付费API。

## 学员安装包

Git只保留源代码、框架、依赖锁与下载地址，不提交三种便携Python、wheel缓存、node_modules和生成的ZIP。已有学员包可继续使用；要重建时：

```sh
python scripts/dev.py prepare
python scripts/fetch_release_assets.py
# 先完成前端 npm ci 与 npm run build
python scripts/build_release.py
```

便携Python按 `assets/runtime-manifest.json` 的锁定URL与SHA下载。wheel按完整依赖锁与三个目标平台下载，网络不可用时保留缓存与错误。发布产物在 `artifacts/`，打包仅允许源代码及明确依赖，不读取本机data、账号或已有学员输出。重建后仍需在独立空白目录验收，不能把“打包成功”等同于真实安装通过。

## 当前验证范围

- 学员版1.0.0曾在Windows用独立空白目录实际离线安装、启动，并验证原版卡生成、接回与网页交互。
- Mac Apple Silicon / Intel有对应运行时、依赖与脚本，尚未完成Mac实机启动、登录及采集验收。
- 发布、转写、后台数据等扩展需要学员自己的连接和相应环境；定时任务需要本机服务运行。代码仓库不会带入任何平台登录态。

冻结方法与第三方源码各自保留原许可及课程授权范围。当前私有仓库不意味着重新授予原框架或上游源码统一开源许可，详见 `assets/workbench/NOTICE.md` 和随包LICENSE。
