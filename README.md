# 🌅 每日看板

三栏式每日信息看板：**每日古诗 · 每日科技简报 · 每日提醒**，支持推送预览与定时推送到**企业微信群机器人**。

零依赖（Python 标准库实现），无需 `pip install`。

## 快速开始

```bash
python server.py        # 或直接双击 start.bat
```

打开 <http://localhost:3000>（启动后会自动打开浏览器）。

- **右上角「设置」**：输入管理密码（默认 `admin123`）进入管理页面
- 管理页可配置：企业微信机器人、AI 助理、定时推送时间，每项均有**推送预览**按钮
- 修改密码：管理页底部「修改管理密码」

## 功能说明

| 栏目 | 数据来源 | 说明 |
| --- | --- | --- |
| 📜 每日古诗 | 今日诗词 API（`v1.jinrishici.com`） | 断网自动回退到内置本地诗库，可点「换一首」 |
| 🤖 每日科技简报 | 多源聚合：60s日报 + 微博热搜 + 头条热榜 + 抖音热点 | 科技类新闻自动置顶并标注来源；热榜实时更新，缓存 30 分钟自动刷新；配置 AI 后由 AI 整理成简报 |
| ⏰ 每日提醒 | 自己添加 | 支持勾选完成、删除，随看板持久化保存 |

### 企业微信机器人

1. 在企业微信里打开目标群聊 → 右键群设置 → **添加群机器人**
2. 复制生成的 Webhook 地址（形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）
3. 粘贴到管理页「企业微信机器人」→ 点击 **推送预览（测试消息）** 验证

### AI 助理（管理科技简报）

支持任意 **OpenAI 兼容**接口，在管理页填写：

- API 地址：如 `https://api.openai.com/v1`、`https://api.deepseek.com/v1`、智谱/Kimi 及各类中转地址
- API Key、模型名（如 `gpt-4o-mini`、`deepseek-chat`、`glm-4-flash`）
- 简报生成提示词（可自定义编辑风格）

配置后点「测试 AI 连接」验证，点「✨ 生成简报预览」查看效果，「🔔 推送简报预览」直接发到群里。

### 定时推送

- 每个栏目可独立开启/关闭并设置推送时间（如 08:00）
- 定时推送由本地服务执行，**需保持 `python server.py` 常驻运行**
- 当天已推送过会自动去重；修改时间并保存后当天生效
- 推送结果可在管理页「推送日志」中查看

## 目录结构

```
daily-board/
├── server.py            # 后端服务（零依赖）
├── start.bat            # Windows 一键启动
├── Dockerfile           # Docker 镜像构建
├── docker-compose.yml   # Docker 编排（端口可用 PORT 变量）
├── push.py              # GitHub API 备用推送通道（git 被阻断时用）
├── public/              # 前端页面
│   ├── index.html
│   ├── style.css
│   └── app.js
└── data/                # 运行时自动生成（不入库）
    ├── config.json      # 配置（密码为哈希存储）
    ├── reminders.json   # 提醒数据
    ├── pushlog.json     # 推送日志
    └── cache/           # 每日古诗 / 简报缓存
```

## Docker 部署（推荐用于定时推送）

定时推送要求服务常驻，用 Docker `restart: unless-stopped` 最省心：

```bash
docker compose up -d --build     # 构建并后台启动
docker logs -f daily-board       # 查看日志
docker compose down              # 停止
```

- 访问 <http://localhost:3000>；容器时区已设为 Asia/Shanghai，定时推送按北京时间触发
- `./data` 挂载为数据卷：配置、提醒、缓存持久化，重建容器不丢失
- 国内拉取基础镜像慢/失败时，先从镜像源拉取再构建：
  ```bash
  docker pull docker.m.daocloud.io/library/python:3.12-slim
  docker tag docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim
  ```

### 自定义端口

通过 `PORT` 环境变量指定宿主机访问端口（容器内固定 3000，不影响数据）：

```bash
PORT=3001 docker compose up -d --build   # 用 3001 端口启动
docker compose down && PORT=3001 docker compose up -d   # 已运行时先停再换端口
docker compose up -d                     # 恢复默认 3000
```

Windows CMD：`set PORT=3001 && docker compose up -d --build`；PowerShell：`$env:PORT=3001; docker compose up -d --build`

不用 compose 时，也可以直接 `docker run` 映射：

```bash
docker run -d --name daily-board -p 3001:3000 -v ./data:/app/data --restart unless-stopped daily-board:latest
```

- 本机 3000 端口被占用时，把 `docker-compose.yml` 里端口映射改成如 `"3001:3000"`，或直接用上面的 `PORT` 变量

## 获取代码 / 拉取更新

仓库：<https://github.com/dll315/daily-board>

```bash
git clone https://github.com/dll315/daily-board.git
cd daily-board
python server.py
```

**网络受限时的备用通道**（github.com 直连被阻断、但 api.github.com 可用时）：

- 推送更新：`python push.py "提交说明"`（走 GitHub API，需本机 `gh` CLI 已登录）
- 拉取最新代码包：<https://api.github.com/repos/dll315/daily-board/tarball/main>
  （curl 下载：`curl -L -o daily-board.tar.gz https://api.github.com/repos/dll315/daily-board/tarball/main`）

> `data/` 目录不入库：密码、API Key、Webhook、提醒等均为各机器本地数据，换机部署后需重新配置。

## 常用环境变量

- `PORT=3000`：服务端口。直接运行时是服务监听端口；Docker compose 里是**宿主机**访问端口（容器内固定 3000），如 `PORT=3001 docker compose up -d`
- `NO_OPEN=1`：启动时不自动打开浏览器（Docker 镜像内已默认设置）
