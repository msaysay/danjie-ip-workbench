---
name: danjie-owner-ip-workbench-student
description: 安装并使用蛋解老板IP工作台，沿用本人的蛋蛋作业生成原版交互卡、选题和完整脚本，并接回网页持续改稿。用于本课程Windows/Mac学员；不代登录、审稿或发布。
---

# 蛋解老板IP工作台（学员版）

本Skill也可作为轻量入口单独导入。若本目录没有assets/workbench，先读references/运行包定位.md；后续所有scripts、assets和运行时路径均使用实际运行包根目录，不使用轻量入口的缓存目录。

## 第一次：安装并打开

用户说“安装/启用/打开工作台”时，定位本SKILL所在目录。先把整个Skill文件夹复制到用户指定可写目录；未指定时用桌面“蛋解工作台”。存在旧安装就先读取，不覆盖旧业务、数据和版本。Windows桌面位置可用系统的Desktop目录，Mac用`~/Desktop`。不要在Skill缓存里经营学员数据。

在工作副本执行：Windows用`cmd /c "启动-Windows.cmd" --no-browser`，Mac用`/bin/sh "启动-Mac.command" --no-browser`。包内含三种Python运行时及核心离线依赖，无需Node、Git、系统Python、管理员权限。在WorkBuddy内置浏览器打开启动输出的网址；没有内置预览时提供可点击的本机链接。实际读取启动输出和`/api/health`，确认data_dir属于这个副本；已有其他服务占端口时不停止它，使用启动参数`--port 新端口`。保留完整原包，不能只复制一个HTML。

已有安装时，先读取`~/.danjie-workbench/locations.json`找到本人的已登记工作目录；文件不存在再看本次用户指定位置。只查当前业务的公开成果与共享文件夹，不读取WorkBuddy私有聊天数据库、其他用户文件或账号凭据。

## 第二步：接住本人的作业

先读`references/工作流.md`。明确本人称呼和这次业务；已有客户卡/人设/原版13项目就实际读取并复用，不重新问整套问题。没有做过的才按相应原版SKILL一步步带着做。不能用老师、其他学员或课堂模拟回答补空。

由AI运行本包`scripts/student_profile.py --owner 本人确认称呼 --business 本次业务 --mode real`创建/复用空白业务。Python用工作副本`.runtime/python/python.exe`（Windows）或`.runtime/python/bin/python3`（Mac）；脚本位于副本根目录，回填程序位于`assets/workbench`。只有用户明确要求模拟才用fictional_demo，不伪造真实回答或确认。

启动会展开12项冻结方法到`assets/workbench/frozen-skills-v041`。按任务只读相应SKILL和必要引用，保留原程序、品牌模板、取材规则与事实缺口。执行原脚本统一加`-X utf8`，避免Windows默认编码破坏中文。09在Windows使用`runtime-fixes/09`的换行兼容副本；Mac可用原09。只修复了UTF-8写入，未放宽源文核对。

## 做完直接接回

WorkBuddy 与 Codex 使用同一条接回。Codex 从仓库根目录的 `AGENTS.md` 进入；下面的命令两边相同。

使用同一本机工作台的`/api/methods/ai-instructions`取得当前业务的接回说明；端口以`assets/workbench/data/service.json`为准。按实际输出写清单，由AI执行`assets/workbench/workbuddy_publish_method.py --manifest 本次清单`，或执行等价的`scripts/publish_method.py --manifest 本次清单`。不让学员填写JSON。只接明确输出文件，保留旧版。原版13项目只读其登记的公开成品，不读runtime采访私有状态。

确认选题后按蛋蛋框架写完整自然口播：03或07开头→04一条贴题主路线→05已有实力/真实身份→06一个收尾。不是把四张卡拼贴，不用学员重复选择全部方法。无真实证据只讲核对办法/明确假设，不编成绩、故事或研究；对比先在内部草稿做，未经核对的版本不交给真实客户试错。服务与公开入口未确认，就不加报名、私信领取或效果保证。

每次写稿前都执行`/api/experience/business/prepare`。它会按当前作业刷新共有目录，不要沿用准备之前的旧格式。读取它返回的本业务共有目录，按其中最新“写稿时沿用的方法.md”“当前作业版本.json”“选题回传格式.md”保存完整稿到“今日选题.json”。`generated_by` 填写实际宿主，不要求写成 WorkBuddy。`source_shas` 只引用本题上下文里的作业。然后调用 sync 并读回。写完在方法页自己点题，接到选题脚本页审核；文件或默认高亮不是本人确认。初稿仍待审，不能标ready或自动发布，也不要代替学员把稿交给 StoryCue。

脚本由学员在页面上确认后，选题脚本页可以「交给 StoryCue 访谈」，原来的下载仍作兜底。访谈要先在设置里完成 StoryCue 向导：本机目录与 bridge-token、桌面 AI（`npm run desktop:connect -- --host workbuddy` 或 `--host codex`、`npm run desktop:login`、`npm run desktop:doctor`）、火山引擎语音控制台的豆包语音 Key、追问用的文字模型。Key 只写入 StoryCue 的 `.env.local`。启动时带 `VOICE_RELAY_PORT=8866`（StoryCue 默认也是 8866），避免和本工作台端口冲突。bridge-token 在 StoryCue 目录的 `.storycue-data/bridge-token`。选题编号只能是字母、数字、下划线和连字符。脚本超过 10 万字要先缩短，背景仍压到 1200 字。访谈结果回到该选题。不要接 sayFrame，也不要打开工作台里的剪辑。成片由学员在外部剪好，到发布页上传。发布仍要学员自己输入「确认发布」。同步若返回 errors，把原因告诉学员。

## 持续记忆与其他功能

每次新对话先读取已登记目录中本次业务的“从工作台接着用的稿件.md”和“以后都要沿用的要求.md”，最新正文及明确修改意见优先，旧稿作历史。网页版修改后同步，再读回核对。记忆是可检查的本地文件，不宣称自动读取了未授权聊天或验证了长期业务效果。

灵感、发布、复盘需要学员自己的连接；流程见`references/可选连接.md`。安装包没有任何老师账号、密钥、Cookie、作品或经营数据。登录/验证码由本人操作；发布前仍要本人确认，不自动投流。任何执行失败保留原文件，定位本次错误后针对性修复；原模块有更严格次数上限时按原要求，不改校验器绕过。
