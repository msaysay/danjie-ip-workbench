# 蛋解老板IP工作台（Codex 入口）

Codex 与 WorkBuddy 走同一条学员回路。WorkBuddy 仍读根目录 `SKILL.md`。这里只补 Codex 需要的入口，不另做一套回填。

运行包根目录必须同时有 `启动-Windows.cmd`、`启动-Mac.command` 和 `assets/workbench/server.py`。本地开发按 `README.md`：Python 3.12 虚拟环境、`python scripts/dev.py prepare`、在 `assets/workbench` 执行 `npm ci && npm run build`、再 `python scripts/dev.py serve`。数据只写当前副本的 `assets/workbench/data`。

## 回路

1. 先读 `references/工作流.md`。已有作业先读已有；缺哪项再按 `assets/workbench/frozen-skills-v041` 里对应的原版 SKILL 做。不要用其他人的答案补空。执行原脚本加 `-X utf8`。
2. 服务已启动后，用本副本的 Python 运行 `scripts/student_profile.py --owner 本人确认称呼 --business 本次业务 --mode real`。只有用户明确要求模拟时才用 `fictional_demo`。
3. 方法成品接回：在本次结果目录写清单，再执行下面任意一条。两条调用同一个发布程序。

```sh
python assets/workbench/workbuddy_publish_method.py --manifest 本次接回清单.json
python scripts/publish_method.py --manifest 本次接回清单.json
```

清单字段以 `GET /api/methods/ai-instructions` 为准。只列这次目录里的成果，不上传安装包、密钥、Cookie 或采访私有状态。导入不是本人确认。

4. 选题和完整口播：先 `POST /api/experience/business/prepare`。它会按当前作业刷新共有目录，不要在准备之前读旧格式。然后读该目录里的 `宿主AI维护说明.md`、`写稿时沿用的方法.md`、`当前作业版本.json`、`选题回传格式.md`。
5. 把今天的题和完整口播写入该目录的 `今日选题.json`。`generated_by` 写 `Codex`，不要写成 WorkBuddy。`source_shas` 只填本题上下文里仍在使用的作业 sha256。`writing_material_version` 必须复制刚读到的值。初稿不要标成已确认，不要自动发布或投流。
6. `POST /api/experience/business/sync`，读回错误和题目。页面上由学员选题、改稿、保存。保存后的正文在 `从工作台接着用的稿件.md`。

没有配置写作模型时，工作台不会自己编脚本。宿主把稿写进 `今日选题.json` 再同步，就是这条回路的生成步骤。初稿不要标成已确认，也不要代替学员打开访谈。

脚本在页面上确认后，学员可以在选题脚本页交给本机 StoryCue 访谈，或仍下载脚本兜底。访谈前在设置里完成「访谈（StoryCue）」：StoryCue 目录和 bridge-token、`npm run desktop:connect -- --host workbuddy`（Codex 用 `--host codex`）、`npm run desktop:login`、`npm run desktop:doctor`、豆包语音控制台 Key、追问用的文字模型。Key 只经工作台转到 StoryCue 的 `.env.local`。启动 StoryCue 时带 `VOICE_RELAY_PORT=8866`（StoryCue 自己的默认也是 8866）。选题编号须匹配 `^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$`。脚本超过 10 万字或交接包过大时不要硬传，按接口返回的 413 请学员缩短。bridge-token 在 `<StoryCue目录>/.storycue-data/bridge-token`。学员确认脚本之后：访谈是可选项，在选题脚本页交给 StoryCue，或下载脚本自己拍。不要接 sayFrame，也不要打开工作台里的剪辑。成片由学员在外部剪好，到发布页上传。发布仍要学员自己输入「确认发布」。这条写稿回路不自动发布、不改复盘规则、不改 TikHub。同步若返回 errors，把原因告诉学员，保留原文件，不放宽校验。
