# AI 邮件翻译（可选）

登录后的邮件详情页支持手动翻译主题和正文。默认目标语言为简体中文，也可选择繁体中文、英语、日语、韩语、法语、德语、西班牙语。原始主题、正文、附件保持不变；译文独立显示，仅存在于当前页面，切换邮件即清除，不写入数据库、不自动复制或发送邮件。公共邮件分享页不提供翻译接口入口。

### 显示方式与排版

原文始终位于上方，原始 DOM、iframe 内容和已有 CSS 不受翻译动作修改；译文位于其下方的独立可折叠 `<details>` 面板，可随时收起对照原文。HTML 邮件会先从当前已净化的原文文档提取可见文本节点，按节点编号发送；返回后克隆安全 HTML，只替换对应文本节点，保留原有标签、属性、链接、图片、表格和文档样式。译文 iframe 使用 `sandbox="allow-same-origin"`，禁用脚本并设置 CSP，不执行模型返回内容。纯文本邮件也使用克隆的安全文本节点，保留换行及原文排版样式；主题始终以 `textContent` 显示。若没有可翻译的正文文本，仍可翻译主题。译文不回写数据库，也不会改变原文。

## 服务端配置

配置以下服务器进程环境变量并重启应用；不需要新增 Python 依赖（使用已有 requests）。本地 Python 启动不会自动加载 `.env`，请通过运行环境注入。

| 变量 | 说明 |
| --- | --- |
| `AI_TRANSLATION_BASE_URL` | OpenAI-compatible Chat Completions API 基础地址，例如 `https://api.openai.com/v1` |
| `AI_TRANSLATION_API_KEY` | 提供商 Bearer API key，仅服务端使用 |
| `AI_TRANSLATION_MODEL` | 提供商支持的模型名称，例如 `gpt-4o-mini` |
| `AI_TRANSLATION_TIMEOUT_SECONDS` | 可选，总体响应读取截止时间，默认 45 秒，允许 5–90 秒 |

前三项任意缺失时服务禁用（503），详情页仍可查看原文并在点击时提示未配置。不通过前端或设置 API 暴露配置与密钥。

地址规则：

- `https://provider.example` → `https://provider.example/v1/chat/completions`
- `https://provider.example/v1/` → `https://provider.example/v1/chat/completions`
- 自定义路径 `https://provider.example/openai/v1` → 追加 `/chat/completions`
- 已含 `/chat/completions` 的完整地址不会重复追加。

仅允许 HTTP/HTTPS，不允许地址内含用户名、密码、query、fragment。线上务必使用 HTTPS；HTTP 仅适合可信的本地模型服务。地址是管理员环境配置，不接受客户端传入；请仅配置可信的服务商。

### Docker

需要运行包含此功能代码的新镜像（旧的发布镜像没有此功能）。

- 本仓库 `docker-compose.build.yml`：复制 `.env.example` 为 `.env.local`，保留/填好 `SECRET_KEY`，取消注释并填写 AI 变量，执行 `docker compose -f docker-compose.build.yml up -d --build`。该 Compose 已通过 `env_file` 注入全部变量。
- `docker-compose.yml`：四个 AI 变量已支持从宿主进程环境或 Compose 默认 `.env` 插值。配置后执行 `docker compose up -d --force-recreate`；同时确保 `image` 指向包含本功能的镜像。
- `docker run`：用受保护的 `--env-file /path/to/server.env` 注入，不在镜像、仓库或浏览器中保存真实 key。

修改环境后需要重建容器/重启服务器。不要提交 `.env.local` 或真实密钥；本地自行创建的 `.env.local` 也需注意避免被 git 跟踪。反向代理读取超时建议大于 110 秒；Gunicorn timeout 应大于该值（仓库默认 300 秒）。

## 隐私与安全

只有点击“AI 翻译”且确认隐私提示后才提交当前详情页邮件的主题、正文与目标语言。不会自动上传，不提交邮件头、收发件人元数据、账户密码、token 或附件；这些信息如果已经出现在正文中仍会随正文发送。附件内的文字不翻译。链接文字和正文内 URL 可能包含敏感信息，也会作为文本发送，请谨慎确认。

前端从净化后的原文文档复制安全 HTML，跳过 script/style/head/template/noscript、`hidden` 和 `aria-hidden="true"` 元素中的文字，仅发送文本节点，不发送 HTML/CSS、标签属性或图片 URL（除非 URL 本身是正文文字）。兼容旧版 `body_type=html` 接口时，服务端仅提取纯文本。二者都不执行邮件脚本、不访问邮件链接。原文展示沿用项目原有机制；即使启用信任模式，译文克隆也会再次使用 DOMPurify 净化。模型输出只写入 `Text.data` 或主题 `textContent`，不会被解释为 HTML。

限制：这不是完整 CSS 可见性检测，使用 CSS 隐藏的普通元素可能仍被提取；安全净化与 CSP 会剔除危险元素、禁用外部样式/字体等，因此不保证像素级相同。译文长度、字体或容器宽度也会改变换行和高度。正文图片保留原有 URL，浏览器可能再次请求远程图片（包括跟踪像素）；图片中的文字、`alt`/`title` 等属性不翻译、不发送给 AI。细碎的内联文本节点可能影响模型的跨节点语义，请核对原文。

接口依赖现有网页登录认证（包括会话过期检查）与 Flask-WTF CSRF 保护，不支持外部 API key 代替网页登录。新代码不记录邮件内容、模型输出、key 或上游错误详情；错误仅返回固定安全提示。请求关闭重定向、不自动重试，防止 key 随重定向泄漏或重复计费。现有系统代理环境仍可能影响 requests，服务端需信任其运维环境。

模型收到明确 system 指令，将邮件视为不可信数据、不执行正文命令、不调用工具；这降低 prompt injection 风险但无法保证翻译质量或完全抵御恶意邮件。请对照原文核实，不把 AI 输出视为可信指令。提供商处理和保存数据遵循其政策，应用无法保证提供商不保留数据。

## 接口与限制

`POST /api/email/translate`，详情页使用分段 JSON（需网页登录及有效 `X-CSRFToken`）：

```json
{"subject":"Hello","segments":[{"id":0,"text":"Hello "},{"id":1,"text":"World"}],"target_language":"zh-CN"}
```

成功返回：

```json
{"success":true,"translation":{"subject":"你好","segments":[{"id":0,"text":"你好 "},{"id":1,"text":"世界"}],"target_language":"zh-CN"}}
```

`segments` 必须是数组，每项恰有 `id`（从 0 连续递增的整数，不接受布尔值）及非空 `text` 字符串；最多 400 段、合计 30,000 字符。响应严格校验字段、顺序、数量、非空字符串与长度，缺失、重复或乱序均拒绝，不做部分渲染。禁止同时提交 `segments` 和 `body`。空数组仅允许有非空主题。节点边界原有空白由前端保留，避免模型去除空白导致内联词语粘连。

也兼容原来的纯文本/HTML 正文请求；这一路径只返回纯文本，不用于详情页保留 HTML 排版：

```json
{"subject":"Hello","body":"World","body_type":"text","target_language":"zh-CN"}
```

`body_type` 允许 `text`/`html`；缺省为 `text`。目标语言缺省为 `zh-CN`。成功返回：

```json
{"success":true,"translation":{"subject":"你好","body":"世界","target_language":"zh-CN"}}
```

输入/上游错误使用对应 400/413/429/502/503/504 状态和 `{"success":false,"error":{"code":"...","message":"安全提示"}}`；认证/CSRF 错误沿用项目格式。翻译响应加 `Cache-Control: no-store`。

- JSON 请求最多 128 KiB；主题最多 2,000 字符；纯文本正文最多 30,000 字符；原 HTML 最多 60,000 字符，提取后最多 30,000 字符。字符数按 Python Unicode 字符计数。
- 空主题加空正文拒绝；超长内容明确拒绝，不默默截断。
- 每进程最多 2 个并发请求；满时立即 429，不排队。多 worker 分别计数；未实现跨进程限流、用户配额或计费管理，公开部署建议额外配置网关限流。
- 一次非流式 Chat Completions 请求，`temperature=0`，`max_tokens=4096`。模型需支持这些参数并返回 JSON 字符串（分段模式为 `subject`/`segments`，兼容正文模式为 `subject`/`body`）；不强制可选 `response_format`，以兼容更多服务。拒绝 `finish_reason=length`，不展示被截断的结果。
- 响应最多 128 KiB，译文也需满足主题/正文字符限制。输入虽在上限内，长邮件仍可能超过模型上下文或输出预算；当前版本不会分块、重试、后台翻译或缓存。
- 连接超时最多 5 秒；socket 无数据读取超时为配置值；逐字节读取时检查整体 deadline，防止持续 trickle 无限制占用。requests 不是强制 wall-clock 取消机制：一次等待可超出 deadline 至最多一个读取超时，DNS 解析受系统 resolver 行为影响。浏览器请求 110 秒后取消；关闭页面/切换详情中止客户端请求不会保证已经开始的上游请求立即取消。

## 测试

```sh
python -m pytest tests/test_ai_translation.py -q
node --check static/js/index/05-emails.js
```

测试完全 mock 上游，不上传真实邮件、不使用真实 key。覆盖登录/会话过期/CSRF、配置缺失和错误、地址拼接、输入及请求大小、HTML 提取、分段输入/输出格式及边界、异常及过长模型响应、超时、并发限制、隐私和安全 DOM 渲染契约。

可选的真实 DOM 回归测试（测试依赖仅安装到临时目录，不影响部署）：

```sh
mkdir -p /tmp/translation-dom-tests
npm install --prefix /tmp/translation-dom-tests --no-audit --no-fund jsdom@22 dompurify
NODE_PATH=/tmp/translation-dom-tests/node_modules node tests/ai_translation_dom.cjs
```

覆盖 HTML 表格/图片/链接/样式保留、纯文本样式和换行、原文 DOM 不变、拒绝不匹配响应、确认前不发送请求，以及模型 HTML 作为文字呈现。jsdom 不提供真实浏览器布局，像素级视觉效果需另行浏览器验证。
