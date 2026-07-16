# 宝塔 Linux 面板生产部署指南

本文适用于将本项目部署到已经运行其他 Python 后端和前端站点的宝塔 Linux 服务器。

推荐方案：独立域名、前端静态部署、FastAPI 使用独立虚拟环境和独立本机端口、Nginx 同域反向代理 `/api`。

**前提限制：** 本系统必须使用独立域名或子域名（例如 `order.example.com`）。不要挂到已有站点的子路径（如 `existing.com/order/`），当前前后端未配置 `basename` / 路径前缀，子路径部署会失败。

## 一、部署结构

```text
浏览器
  └─ https://<DOMAIN>
       ├─ /                -> 宝塔 Nginx -> frontend/dist
       ├─ /api/*           -> 127.0.0.1:18180 -> FastAPI
       └─ /health          -> 127.0.0.1:18180 -> FastAPI

FastAPI
  └─ 当前远程 MySQL / wins_order_book
```

这样部署有以下优点：

- 不占用已有 Python 项目的端口和虚拟环境。
- 不修改已有前端站点或 Nginx 全局配置。
- 后端端口不暴露到公网，仅由本机 Nginx 访问。
- 前端与 API 同源，登录刷新 Cookie 和 CORS 配置最简单。
- 前端由 Nginx 直接提供静态文件，不运行 Vite 开发服务器。

本文使用以下占位符，执行时替换为实际值：

- `<DOMAIN>`：本系统独立域名或子域名，例如 `order.example.com`。
- `<APP_ROOT>`：项目目录，本文使用 `/www/wwwroot/wins-order`。
- `<BACKEND_PORT>`：后端本机端口，本文默认 `18180`；若被占用可改为 `18181` 等，并同步修改启动命令与 Nginx。
- `<DB_HOST>`：数据库地址。当前开发配置为 `115.190.182.82`；若 MySQL 与宝塔在同一台机器，应改为 `127.0.0.1`。
- `<BAOTA_SERVER_IP>`：宝塔服务器访问异机数据库时的出口 IP（公网或内网，以实际能连通为准）。

## 二、上线前必须处理的安全项

### 1. 远程数据库沿用当前配置

生产继续使用现有库 `wins_order_book`，不需要重新建库或清理数据。数据库连接与当前 `backend/.env` 保持一致：

```text
主机：115.190.182.82（同机则用 127.0.0.1）
端口：3306
库名：wins_order_book
用户：root
密码：与当前 backend/.env 中 DATABASE_URL 相同
```

部署前确认连通性：

1. **MySQL 与宝塔同机**：`DATABASE_URL` 的 host 写 `127.0.0.1`，不要绕公网 IP。
2. **MySQL 在另一台机器**：在数据库侧安全组 / 防火墙放行宝塔出口 IP 访问 `3306`；本机 Windows 能连不代表宝塔服务器也能连。优先使用内网地址。

从宝塔服务器测试：

```bash
nc -vz <DB_HOST> 3306
```

说明：继续使用 root 便于与当前开发环境一致、减少账号改造成本。若后续要加强权限隔离，可再拆分只读/迁移账号；本文不强制。

### 2. 生成新的 JWT 密钥

不要沿用开发环境的 `JWT_SECRET`。在宝塔终端执行：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

保存输出，后续写入后端生产 `.env`。

### 3. 关闭公网自助注册

当前系统的登录页包含“创建账套”，后端 `/api/v1/auth/register` 也允许匿名注册。正式管理员已经存在后，公网部署必须阻止该接口，否则任何访问者都能创建新账套。

本文在 Nginx 中增加精确拦截：

```nginx
location = /api/v1/auth/register {
    return 404;
}
```

这会保证后端注册接口不可访问。前端目前仍会显示“创建账套”入口，但提交会被拒绝；后续可再增加生产环境注册开关，从前后端同时隐藏和禁用该功能。

### 4. 关闭接口文档入口（建议）

应用在 `ENVIRONMENT=production` 时会关闭 `/docs`，但默认仍可能暴露 `/openapi.json`。建议在本站点 Nginx 中一并拦截：

```nginx
location = /docs {
    return 404;
}

location = /openapi.json {
    return 404;
}

location = /redoc {
    return 404;
}
```

## 三、检查服务器环境和端口

### 1. 宝塔软件要求

建议版本：

- Nginx：宝塔当前稳定版本。
- Python：3.11。
- Node.js：22 LTS，仅用于在服务器上构建前端；若内存紧张或已有其他前端依赖全局 Node 版本，可改为本机构建后只上传 `frontend/dist`（见第六节）。
- 宝塔 Python 项目管理器：用于进程守护和日志管理。

不要复用已有 Python 服务的虚拟环境。每个项目独立安装依赖，避免 FastAPI、SQLAlchemy 或 Uvicorn 版本互相影响。

切换宝塔「Node 版本管理」中的全局版本前，确认不会影响服务器上其他前端项目的构建脚本。

### 2. 检查端口

先确认 `18180` 未被已有服务占用：

```bash
ss -lntp | grep ':18180 '
```

没有输出表示端口通常可用。如果已占用，例如改用 `18181`：

```bash
ss -lntp | grep ':18181 '
```

确认新端口后，需要同时修改：

1. 宝塔 Python 项目的 Uvicorn 启动命令中的 `--port`。
2. Nginx `/api/` 和 `/health` 的 `proxy_pass` 地址。

不要在云安全组或宝塔防火墙开放 `18180`（或你改用的后端端口）。后端只监听 `127.0.0.1`。

也可用下面命令快速查看已被监听的端口，避免与已有 Python / 其他服务冲突：

```bash
ss -lntp | grep -E ':(80|443|8000|8080|5173|18180|18181) '
```

## 四、上传代码并建立独立环境

### 1. 项目目录

```bash
mkdir -p /www/wwwroot/wins-order
cd /www/wwwroot/wins-order
```

可以通过 Git 拉取，也可以通过宝塔文件管理上传。上传时不要包含以下本地文件：

```text
backend/.env
backend/.venv/
frontend/.env.local
frontend/node_modules/
frontend/dist/
```

若采用本机构建前端，可单独上传已构建的 `frontend/dist/`，并跳过服务器上的 `npm ci` / `npm run build`。

最终目录应类似：

```text
/www/wwwroot/wins-order/
├─ backend/
├─ frontend/
├─ docs/
└─ README.md
```

### 2. 后端虚拟环境

虚拟环境路径二选一，不要混用：

- **方式 A（推荐，与本文命令一致）**：在项目内手动创建 `backend/.venv`，Python 项目启动命令指向该路径。
- **方式 B**：完全使用宝塔 Python 项目管理器自动创建的虚拟环境（常见路径含 `*_venv` 或 `/www/server/pyporject_evn/...`），依赖也装进该环境，启动命令使用该环境中的 `uvicorn`。

方式 A：

```bash
cd /www/wwwroot/wins-order/backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果宝塔安装的 Python 3.11 路径不同，在软件商店或 Python 项目管理器中复制实际解释器路径。

### 3. 后端生产配置

在 `/www/wwwroot/wins-order/backend/.env` 写入。其中 **仅 `DATABASE_URL` 沿用当前远程库配置**；其余项必须按生产环境填写，不能照搬开发机上的 `FRONTEND_ORIGIN` / `SECURE_COOKIES` / `JWT_SECRET` / `ENVIRONMENT`。

同机 MySQL 示例：

```dotenv
ENVIRONMENT=production
DATABASE_URL=mysql+pymysql://root:<DB_PASSWORD>@127.0.0.1:3306/wins_order_book?charset=utf8mb4
JWT_SECRET=<NEW_RANDOM_JWT_SECRET>
FRONTEND_ORIGIN=https://<DOMAIN>
SECURE_COOKIES=true
```

异机 MySQL（与当前开发配置同主机）示例：

```dotenv
ENVIRONMENT=production
DATABASE_URL=mysql+pymysql://root:<DB_PASSWORD>@115.190.182.82:3306/wins_order_book?charset=utf8mb4
JWT_SECRET=<NEW_RANDOM_JWT_SECRET>
FRONTEND_ORIGIN=https://<DOMAIN>
SECURE_COOKIES=true
```

将 `<DB_PASSWORD>` 替换为当前 `backend/.env` 中的数据库密码。若密码包含 `@`、`/`、`:`、`#`、`%` 等字符，必须进行 URL 编码；普通字母数字和末尾 `.` 一般无需编码。

注意：

- `FRONTEND_ORIGIN` 必须与浏览器地址完全一致，不要带末尾 `/`。
- 使用 HTTPS 时必须设置 `SECURE_COOKIES=true`。
- `.env` 必须位于 `backend` 目录，因为应用按后端工作目录读取它。

限制文件权限，并让宝塔 Python 项目的运行账号拥有读取权限。宝塔 Linux 常见运行账号为 `www`；如果项目管理器显示其他运行账号，请同步替换：

```bash
chown www:www /www/wwwroot/wins-order/backend/.env
chmod 600 /www/wwwroot/wins-order/backend/.env
```

不要把 `.env` 放进前端 `dist`，也不要提交到 Git。

## 五、数据库迁移

数据库中已经存在正式管理员和业务表，不要再运行以下脚本：

```text
scripts.seed_demo
scripts.prepare_production_db --apply
scripts.init_local_db
```

首次部署先确认 Alembic 版本状态：

```bash
cd /www/wwwroot/wins-order/backend
source .venv/bin/activate
alembic current
```

按结果处理：

1. **已显示最新 revision（例如 `4bcb1229f7af`）**：无需操作，或执行 `alembic upgrade head`（空操作）。
2. **库中业务表已存在，但没有 `alembic_version` / `alembic current` 为空**：不要直接 `upgrade head`（会尝试重复建表并失败）。在确认表结构已与当前代码一致后执行：

```bash
alembic stamp head
alembic current
```

3. **库较旧、需要补迁移**：先备份数据库，再执行：

```bash
alembic upgrade head
alembic current
```

迁移与常驻进程共用生产 `.env` 中的 `DATABASE_URL`（当前为 root + 远程库）。执行前确认工作目录为 `backend`，且已激活正确虚拟环境。

## 六、构建前端

### 方案 A：在服务器上构建

```bash
cd /www/wwwroot/wins-order/frontend
npm ci
VITE_API_BASE_URL=/api/v1 npm run build
```

构建完成后应存在：

```text
/www/wwwroot/wins-order/frontend/dist/index.html
```

`npm run test` / `npm run lint` 建议在开发机或 CI 执行，不要作为服务器上线的硬性步骤；小内存机器上同时跑测试与构建容易失败或影响已有服务。

### 方案 B：本机构建后上传（内存紧张或 Node 版本冲突时推荐）

在开发机：

```bash
cd frontend
npm ci
VITE_API_BASE_URL=/api/v1 npm run build
```

将生成的 `frontend/dist/` 上传到服务器 `/www/wwwroot/wins-order/frontend/dist/`，并设置可读权限（见第八节）。

不要在生产环境执行：

```bash
npm run dev
```

Vite 开发服务器不负责生产静态资源、TLS、缓存和进程安全。

## 七、在宝塔创建后端 Python 项目

在宝塔面板进入“网站”或“Python 项目管理器”，新增 Python 项目。不同版本的宝塔界面名称可能略有差异，核心参数如下：

```text
项目名称：wins-order-backend
项目目录：/www/wwwroot/wins-order/backend
工作目录：/www/wwwroot/wins-order/backend
Python 版本：3.11
虚拟环境：/www/wwwroot/wins-order/backend/.venv
启动方式：自定义命令
启动命令：/www/wwwroot/wins-order/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18180 --workers 2
开机启动：开启
守护进程：开启
```

若改用其他端口（如 `18181`），把命令里的 `--port` 改掉即可。

重要：

- **不要点击 Python 项目的「映射」**。映射会额外生成反代或端口规则，容易与本文独立站点 + 手写 Nginx 冲突，也可能诱导开放后端端口。本系统的公网入口只走第八、九节的静态站点。
- 若面板强制使用自建 venv，把启动命令中的 `uvicorn` 路径改成面板给出的绝对路径，并保证依赖装在同一环境。
- 工作目录必须是 `backend`，否则读不到 `.env`，也无法导入 `app`。

资源建议：

- 服务器内存不足 2 GB，或已有其他 Python 服务占用较多内存：先使用 `--workers 1`。
- 服务器内存 2 GB 及以上且较空闲：可从 `--workers 2` 开始。
- 不要盲目增加 worker；每个 worker 都会建立独立数据库连接池并占用内存。

启动后先在服务器本机验证：

```bash
curl -i http://127.0.0.1:18180/health
```

预期结果：

```json
{"status":"ok"}
```

生产环境设置了 `ENVIRONMENT=production` 后，`/docs` 应不可访问；再配合第二节 Nginx 拦截 `/openapi.json`。

如果 Python 项目管理器无法使用自定义命令，也可使用宝塔 Supervisor 管理同一命令，但同一个后端只能由一个守护工具启动，避免重复占用端口。

## 八、在宝塔创建前端站点

在宝塔“网站”中新增站点：

```text
域名：<DOMAIN>
根目录：/www/wwwroot/wins-order/frontend/dist
PHP 版本：纯静态
数据库：不创建
```

不要把站点根目录设置为项目根目录或 `backend` 目录，否则可能将 `.env`、源码和日志暴露给公网。

确保 Nginx 运行账号能够读取静态文件：

```bash
chown -R www:www /www/wwwroot/wins-order/frontend/dist
find /www/wwwroot/wins-order/frontend/dist -type d -exec chmod 755 {} \;
find /www/wwwroot/wins-order/frontend/dist -type f -exec chmod 644 {} \;
```

如果你的宝塔 Nginx 运行账号不是 `www`，请替换为实际账号。

## 九、配置 Nginx 同域反向代理

在宝塔站点设置中打开“配置文件”。保留宝塔生成的 `server`、SSL 和日志配置，只在当前 `<DOMAIN>` 的 `server` 块中加入以下 `location`。

顺序建议如下：

```nginx
# 已有正式管理员，禁止公网匿名创建账套。
location = /api/v1/auth/register {
    return 404;
}

# 生产环境关闭文档与 OpenAPI 描述。
location = /docs {
    return 404;
}

location = /openapi.json {
    return 404;
}

location = /redoc {
    return 404;
}

# FastAPI 接口。proxy_pass 不带结尾斜杠，保留原始 /api/... 路径。
location ^~ /api/ {
    proxy_pass http://127.0.0.1:18180;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_connect_timeout 10s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    proxy_buffering off;
}

# 健康检查单独转发，便于监控和排障。
location = /health {
    proxy_pass http://127.0.0.1:18180/health;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Vite 构建产物可长期缓存；文件名包含内容哈希。
location /assets/ {
    try_files $uri =404;
    expires 30d;
    add_header Cache-Control "public, immutable";
}

# React BrowserRouter 刷新回退到 index.html。
location / {
    try_files $uri $uri/ /index.html;
}
```

注意：

- 只修改新建的 `<DOMAIN>` 站点配置，不修改已有站点配置和 Nginx 全局配置。
- 如果后端端口改为 `18181`，上面 `/api/` 与 `/health` 两个 `proxy_pass` 必须同步修改。
- 不要为 `/api/` 配置静态缓存，否则登录和账务数据可能被错误缓存。
- 宝塔也支持通过“网站 → 站点设置 → 反向代理”添加规则；官方说明见：[宝塔反向代理文档](https://docs.bt.cn/user-guide/site/php/site-config/reverse-proxy)。本项目同时需要 SPA 回退、注册拦截和文档拦截，直接编辑当前站点配置更清晰。

保存前执行 Nginx 配置检查：

```bash
nginx -t
```

检查成功后，在宝塔中重载 Nginx。不要直接停止服务器上已有的 Nginx。

## 十、配置域名和 HTTPS

### 1. DNS

将 `<DOMAIN>` 的 A 记录指向宝塔服务器公网 IP。

等待解析生效：

```bash
nslookup <DOMAIN>
```

### 2. SSL

在宝塔站点的“SSL”中申请 Let's Encrypt 证书：

1. 选择当前域名。
2. 申请证书。
3. 开启强制 HTTPS。
4. 确认证书自动续期任务正常。

服务器安全组和宝塔防火墙只需要对公网开放：

```text
80/tcp
443/tcp
```

`18180`（或你改用的后端端口）不对公网开放。若数据库在异机，仅放行宝塔访问 `3306`。

## 十一、首次上线验证

### 1. 后端进程

```bash
curl -i http://127.0.0.1:18180/health
```

### 2. HTTPS 和反向代理

```bash
curl -i https://<DOMAIN>/health
curl -I https://<DOMAIN>/
curl -I https://<DOMAIN>/orders
```

预期：

- `/health` 返回 `200` 和 `{"status":"ok"}`。
- `/` 返回前端页面。
- `/orders` 不返回 Nginx 404，而是回退到 `index.html`。

### 3. 注册接口与文档应被关闭

```bash
curl -i -X POST https://<DOMAIN>/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{}'

curl -I https://<DOMAIN>/docs
curl -I https://<DOMAIN>/openapi.json
```

预期均返回 `404`。

### 4. 浏览器验证

使用正式管理员登录，检查：

1. 登录成功并进入仪表盘。
2. 刷新页面后仍能恢复登录状态。
3. 浏览器开发者工具中的 `refresh_token` Cookie 包含 `HttpOnly`、`Secure`、`SameSite=Lax`。
4. 登记一笔测试订单，确认订单、资金流水和仪表盘同步更新。
5. 测试完成后按正常业务纠错流程处理测试订单，不直接在数据库删除生产数据。

说明：`/health` 当前只证明 FastAPI 进程可访问，不检查 MySQL。成功登录和读取仪表盘才是数据库连接验证。

## 十二、日志位置

常见日志：

```text
宝塔 Python 项目管理器：wins-order-backend 项目日志
Nginx 访问日志：/www/wwwlogs/<DOMAIN>.log
Nginx 错误日志：/www/wwwlogs/<DOMAIN>.error.log
```

实际文件名以宝塔生成的站点配置为准。

后端日志中不要输出 `.env`、数据库 URL、JWT、Authorization 请求头或 Cookie。

## 十三、日常更新流程

建议在业务低峰更新。测试与 lint 优先在开发机或 CI 完成；服务器上只做依赖安装、迁移、构建（或同步 dist）和重启。

```bash
cd /www/wwwroot/wins-order

# 1. 更新前备份当前代码和静态产物；排除虚拟环境和生产密钥。
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_ROOT=/www/backup/wins-order
mkdir -p "$BACKUP_ROOT"
cp -a frontend/dist "$BACKUP_ROOT/frontend-dist-${STAMP}"
tar \
  --exclude='backend/.venv' \
  --exclude='backend/.env' \
  --exclude='*/__pycache__' \
  -czf "$BACKUP_ROOT/backend-${STAMP}.tar.gz" \
  backend

# 2. 更新代码：Git 仓库用 pull；上传部署则跳过本步，改为覆盖上传源码（仍不要覆盖 backend/.env）。
# git pull --ff-only

# 3. 更新后端依赖。
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt

# 4. 按“五、数据库迁移”处理：先 alembic current，再 upgrade 或 stamp。
alembic current
alembic upgrade head

# 5. 构建前端（若使用本机构建，改为上传新的 frontend/dist）。
cd ../frontend
npm ci
VITE_API_BASE_URL=/api/v1 npm run build
```

完成后：

1. 在宝塔 Python 项目管理器中重启 `wins-order-backend`。
2. 不需要重启 Nginx，静态文件更新会立即生效；只有修改站点配置时才重载 Nginx。
3. 重新验证本机 `/health`、公网 `/health`、登录和关键页面。

不要在更新脚本中执行 `scripts.prepare_production_db --apply` 或 `scripts.seed_demo`。

可选：在开发机执行 `cd backend && pytest` 与 `cd frontend && npm run test && npm run lint`，通过后再部署。

## 十四、回滚原则

### 1. 后端或前端代码回滚

如果健康检查失败且数据库迁移没有破坏兼容性：

1. 恢复上一版后端代码或切回上一 Git 版本。
2. 从 `/www/backup/wins-order/frontend-dist-<STAMP>` 恢复上一版静态文件。
3. 在宝塔中重启后端项目。
4. 再次检查 `/health` 和登录。

不要使用 `git reset --hard` 覆盖服务器上的 `.env` 或未备份文件。

### 2. 数据库回滚

- 更新前先通过数据库服务商、宝塔或 `mysqldump` 创建备份。
- 不要默认执行 `alembic downgrade`；只有确认迁移脚本可逆且新数据兼容时才降级。
- 涉及删列、数据转换或不可逆迁移时，优先恢复数据库备份，并同步回滚应用版本。

## 十五、常见故障排查

### 1. 域名返回 502

依次检查：

```bash
ss -lntp | grep ':18180 '
curl -i http://127.0.0.1:18180/health
```

再查看宝塔 Python 项目日志和 Nginx 错误日志。常见原因：

- Python 项目未启动。
- Uvicorn 使用了其他端口。
- Python 项目工作目录不是 `backend`，导致无法加载 `.env` 或 `app`。
- Nginx `proxy_pass` 端口与 Uvicorn 不一致。
- 误用了 Python 项目「映射」，与当前站点反代冲突。

### 2. 前端页面刷新后 404

确认 Nginx 当前站点存在：

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### 3. 登录提示 CORS 错误

确认后端 `.env`：

```dotenv
FRONTEND_ORIGIN=https://<DOMAIN>
```

必须与浏览器地址的协议、域名和端口完全一致，并重启后端项目使配置生效。

同域部署时，前端必须以以下方式构建：

```bash
VITE_API_BASE_URL=/api/v1 npm run build
```

### 4. 登录成功但刷新后退出

检查：

- 站点是否全程使用 HTTPS。
- `SECURE_COOKIES=true` 是否生效。
- 浏览器中的 `refresh_token` 是否带 `Secure` 和 `HttpOnly`。
- Nginx 是否完整代理 `/api/v1/auth/refresh`。
- 浏览器和服务器时间是否准确。

### 5. 后端无法连接远程 MySQL

从宝塔服务器测试网络：

```bash
nc -vz <DB_HOST> 3306
```

再检查：

- `DATABASE_URL` 是否沿用当前库账号，host 在同机时是否为 `127.0.0.1`。
- 异机时安全组是否放行宝塔出口 IP。
- MySQL 用户的 host 是否允许宝塔来源。
- 数据库密码是否正确；含特殊字符时是否已 URL 编码。
- 数据库是否强制 TLS；如强制 TLS，需要在 SQLAlchemy URL 中补充证书参数。

### 6. `/docs` 或 `/openapi.json` 在生产环境仍能打开

确认后端 `.env` 中是：

```dotenv
ENVIRONMENT=production
```

并确认本站点 Nginx 已按第二节拦截 `/docs`、`/openapi.json`、`/redoc`，然后重启后端并重载 Nginx。

### 7. Nginx 配置影响其他站点

- 只编辑 `<DOMAIN>` 对应的站点配置。
- 不修改 Nginx 全局 `nginx.conf`。
- 每次保存前执行 `nginx -t`。
- 通过宝塔“重载”Nginx，不要随意停止 Nginx 服务。

### 8. Alembic 报错表已存在

说明库中已有业务表但未记录迁移版本。确认结构一致后执行 `alembic stamp head`，不要反复 `upgrade head`。

### 9. 虚拟环境或依赖错乱

确认启动命令中的 `uvicorn` 与 `pip install -r requirements.txt` 使用的是同一个 venv，未混用宝塔自动环境与 `backend/.venv`。

## 十六、最终上线检查清单

- 使用独立域名/子域名，未挂到已有站子路径。
- 域名解析到宝塔服务器，HTTPS 有效并强制跳转。
- 前端根目录为 `frontend/dist`，不是项目根目录。
- 后端使用独立 Python 3.11 虚拟环境，未复用其他项目 venv。
- 未使用 Python 项目「映射」；公网入口仅为新建静态站点。
- Uvicorn 只监听 `127.0.0.1:<BACKEND_PORT>`（默认 `18180`）。
- 公网未开放后端端口；已有服务端口未被误改。
- `DATABASE_URL` 沿用当前远程库（同机用 `127.0.0.1`）。
- `JWT_SECRET` 已重新生成，未使用开发密钥。
- `ENVIRONMENT=production`。
- `SECURE_COOKIES=true`。
- `FRONTEND_ORIGIN=https://<DOMAIN>`。
- 前端构建变量为 `VITE_API_BASE_URL=/api/v1`。
- `/api/v1/auth/register`、`/docs`、`/openapi.json` 已被 Nginx 拦截。
- Alembic 已到 `head`（`upgrade` 或必要时 `stamp`）。
- `/health`、登录、刷新登录和页面刷新验证通过。
- 已配置代码、数据库和静态文件备份策略。
