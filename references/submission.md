# 预检与作答回传

## 答案下发：模型侧为权威

参考答案与 rubric 的权威副本只存在于 `sessions/<quiz_id>/quiz.json`。HTML 是否展示，由模式决定：

| 模式 | HTML 中的答案 | 提交后 | 批改后 |
| --- | --- | --- | --- |
| `practice` | 可内嵌 `answer/rubric/explanation` | 页面显示即时反馈，标注“非权威” | 生成报告；可选 review 页 |
| `exam` | 剥离答案与 `sql_context.expected_rows` | 只提示已提交 | 生成 `review.html`，此时才展示答案与解析 |

构建命令：

```bash
# practice：默认注入答案
python build_exam.py ... --mode practice

# exam：自动剥离答案
python build_exam.py ... --mode exam --include-answers auto

# 强制不注入（任何模式）
python build_exam.py ... --include-answers never
```

主观题即使出现在练习模式的 HTML 中，也只作为“即时反馈”，不能由 JS 仲裁分数；最终得分一律由 Agent 复算。

## 图片作答

题目带 `allow_image: true` 时，页面会显示“上传图片 / 拍照”，浏览器内压缩为最长边 2000px 的 JPEG，最多 3 张（可配 `max_attachments`）。

提交数据形如：

```json
{
  "qid": "q09",
  "response": "补充说明（可空）",
  "attachments": [
    { "name": "work.jpg", "media_type": "image/jpeg",
      "data_base64": "...", "width": 1600, "height": 1200, "size": 480000 }
  ]
}
```

各通道处理：

| 通道 | 处理方式 |
| --- | --- |
| localhost 接收器 | 自动解码到 `sessions/<quiz_id>/media/qNN-1.jpg`，并把 `data_base64` 替换为 `path`；提交体上限默认 50MB，单图上限 12MB |
| 下载 | JSON 内含 base64；收到后运行 `python scripts/extract_attachments.py --submission <path>` |
| 剪贴板 | 含图片时页面会跳过剪贴板（太大）；改用下载 |
| 浏览器自动化 | 从页面状态取 data URL，自行写文件 |
| 用户粘贴 | 不建议；base64 很长，容易截断 |

只接受 `image/jpeg`、`image/png`、`image/webp`。HEIC 等浏览器无法解码的格式会让用户改用 JPG/PNG。

## 为什么需要协议

浏览器里的作答数据不会自己出现在 Agent 的文件系统里。不同平台能力差异很大，必须**先探测、再选通道、最后校验**。

## 一、预检

会话开始时探测并把结果写入 `.ppt-tutor/capabilities.json`：

| 项目 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Python | `python --version` / `py --version` | `python3 --version` | `python3 --version` |
| 剪贴板 | `powershell -c Get-Clipboard` 或 `clip` | `pbpaste` | `xclip -o -selection clipboard` |
| 下载目录 | `%USERPROFILE%\Downloads`（可能被浏览器改写） | `~/Downloads` | `~/Downloads` |
| 浏览器自动化 | 检查是否存在浏览器类 MCP / computer-use | 同左 | 同左 |

判定档位：

- **A**：Python 3 可用 → 全功能。
- **B**：无 Python，但能解压/读文本/调用 LibreOffice → 抽取降级。
- **C**：只有文件读写 → 下载/剪贴板回传，命题质检改为人工清单。

预检结果只写一次；环境变化时重新探测，不要每轮重复执行。

## 二、五级回传通道

按顺序尝试，前一个成功就不必依赖后面的；但**提交时同时触发多个通道**能显著提高成功率：

### 1. browser_automation

适用：ZCode browser-use、Playwright/Puppeteer MCP 等。

```text
打开 file:///.../exam.html
等待用户点击提交（或由 Agent 代填）
page.evaluate(() => localStorage.getItem('pptTutorDraft:<quiz_id>'))
或直接读取 DOM / 调用页面导出的 buildSubmission()
写入 sessions/<quiz_id>/submission.json
```

优点：路径完全可控。缺点：仅部分平台具备。注意不要替用户答题，除非用户明确要求。

### 2. localhost receiver（A 档首选）

```bash
python scripts/receive_submission.py \
  --dir .ppt-tutor/sessions/<quiz_id> \
  --port 8765 --token <random> --open
```

- `build_exam.py --channel post --endpoint http://127.0.0.1:8765/submit --token <random>`
- 页面用 `fetch` 提交，失败自动退回 `sendBeacon`。
- 接收器写入 `submission.json` 后自动退出；超时退出码为 2。
- 若页面通过 `file://` 打开，请求是跨源；脚本已设置 `Access-Control-Allow-Origin: *`，且 `text/plain` 属于简单请求，不会触发预检。

优点：路径确定、无需猜下载目录。缺点：需要 Python 与可用端口。

### 3. download

页面提交时下载 `quiz-<quiz_id>.json`。

- Agent 只在预检得到的下载目录中查找，文件名必须完全匹配。
- 若目录未知，先问用户“文件下载到哪里了”，不要全盘搜索。
- 浏览器可能因策略禁用自动下载；页面同时提供“重新下载 JSON”按钮。

### 4. clipboard

页面提交时把 JSON 写入剪贴板；失败则降级为 textarea + `execCommand`。

Agent 读取：

```bash
powershell -NoProfile -Command Get-Clipboard   # Windows
pbpaste                                        # macOS
xclip -o -selection clipboard                  # Linux
```

优点：三平台都有 shell 通道，通常比找文件更稳。缺点：用户可能复制了别的东西，读到后必须校验 `quiz_id`。

### 5. user_paste

最后兜底：请用户把 JSON 直接粘贴进对话。适用于任何平台，也适用于所有自动通道都失败的场景。

## 三、等待协议

CLI Agent 无法阻塞等待浏览器操作。正确做法：

1. 打开试卷后，明确告诉用户：“答完点提交，然后回来告诉我‘已完成’。”
2. 结束本轮，不轮询、不猜测。
3. 下一轮用户返回后，按五级通道读取；读不到就问“文件下载到哪了 / 能否把 JSON 贴给我”。

不要在没有收到提交的情况下生成分数或掌握度更新。

## 四、提交校验

读取后逐项检查，任一失败都要求重新提交：

- `schema_version` 为 `1.0`
- `quiz_id` 与本卷一致
- `answers` 非空，qid 都在本卷中且不重复
- `submitted_at >= started_at`
- 每题 `response` 类型与该题型匹配（选择题是字符串/数组，主观题是字符串）

不要尝试修复截断的 JSON；不要用“看起来像”的内容补全答案。

## 五、失败处理

| 现象 | 处理 |
| --- | --- |
| 浏览器打不开 | 让用户手动双击 `exam.html` |
| 下载被禁用 | 切剪贴板通道 |
| 剪贴板被占用 | 让用户点“重新下载 JSON”或直接粘贴 |
| 接收器端口被占 | `--port 0` 自动分配，重新生成 endpoint |
| 页面显示“模板未注入数据” | 用 `build_exam.py` 重新生成，不要手改模板 |
| 提交后页面刷新丢答案 | 检查 localStorage 是否被策略禁用，改用下载/剪贴板 |
