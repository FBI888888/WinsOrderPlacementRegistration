# 做单账本

面向放单收购、学生头子分单和散户做单场景的多租户 Web 记账系统。

## 核心口径

- 放单收入可按订单标价或券后价乘折扣计算，每单允许留原因后覆盖。
- 订单成本仅包含实付金额与佣金；垫资、补款和退回属于现金流，不重复计入成本。
- 学生头子佣金和放单折扣按生效日期保存，订单创建时固化费率快照。
- 成功订单自动产生垫资消耗、佣金应付和放单应收三类流水。
- 结算单确认后锁定订单；需要纠错时先冲正结算，再冲正订单。
- 每个租户是独立账套，所有业务查询由后端根据当前登录租户过滤。

## 技术结构

- `frontend/`：React 19、TypeScript、Vite、Ant Design、TanStack Query。
- `backend/`：FastAPI、SQLAlchemy 2、Alembic、MySQL 8。
- `backend/app/modules/`：按 `iam`、`partners`、`orders`、`funds`、`settlements`、`reports` 拆分业务职责。

## 本地开发环境

开发环境默认连接本机 MySQL，不依赖 Docker。需要先在 Windows 安装并启动 MySQL 8 Server。

默认开发数据库配置：

- 地址：`localhost:3306`
- 数据库：`wins_order_book`
- 应用账号：`wins`
- 应用密码：`wins`

这些默认值只用于本机开发，可通过初始化脚本参数或环境变量修改。

### 1. 准备后端环境

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### 2. 初始化本机 MySQL

初始化脚本使用项目自带的 `PyMySQL` 连接 MySQL Server，不要求系统安装 `mysql` 命令行工具。

```powershell
.venv\Scripts\python -m scripts.init_local_db
```

脚本将：

1. 提示输入本机 MySQL `root` 密码。
2. 创建 `wins_order_book` 数据库。
3. 创建本地开发账号 `wins`。
4. 用开发账号重新连接验证权限。
5. 自动生成 `backend/.env`，并保留已有的 `JWT_SECRET`。

如果本机 MySQL 使用其他端口或账号：

```powershell
.venv\Scripts\python -m scripts.init_local_db --host localhost --port 3307 --admin-user root --database wins_order_book --app-user wins --app-password wins
```

管理员密码也可以通过当前 PowerShell 会话临时传入，避免交互输入：

```powershell
$env:MYSQL_ADMIN_PASSWORD="你的本机MySQL管理员密码"
.venv\Scripts\python -m scripts.init_local_db
Remove-Item Env:MYSQL_ADMIN_PASSWORD
```

### 3. 执行数据库迁移

```powershell
.venv\Scripts\alembic upgrade head
```

### 4. 启动后端

```powershell
.venv\Scripts\uvicorn app.main:app --reload
```

后端地址：

- API：http://localhost:8000
- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 5. 启动前端

另开一个终端：

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

前端地址：http://localhost:5173

首次使用在登录页选择“创建账套”，负责人账号会自动获得 `OWNER` 权限。

## 手动配置本地数据库

如果不使用初始化脚本，可以复制后端配置模板并自行修改连接字符串：

```powershell
cd backend
copy .env.example .env
```

`backend/.env` 中的关键配置：

```dotenv
DATABASE_URL=mysql+pymysql://wins:wins@localhost:3306/wins_order_book?charset=utf8mb4
```

密码包含 `@`、`/`、`:` 等字符时需要进行 URL 编码，建议优先使用初始化脚本自动生成。

## 演示数据

完成本地数据库迁移后执行：

```powershell
cd backend
.venv\Scripts\python -m scripts.seed_demo
```

演示账号：`demo@example.com`，密码：`demo12345`。生产环境不要执行该脚本。

## Docker 可选启动

Docker Compose 保留用于快速搭建隔离环境，不是默认开发方式：

```powershell
copy .env.example .env
docker compose up --build
```

## 质量检查

```powershell
cd backend
.venv\Scripts\pytest

cd ..\frontend
npm run test
npm run lint
npm run build
```

## 生产部署注意

- 设置高强度 `JWT_SECRET`，启用 HTTPS，并将 `SECURE_COOKIES=true`。
- MySQL 使用独立账号和强密码，不要暴露数据库端口。
- 部署前执行 `alembic upgrade head`，并为数据库配置定期备份。
- 前端生产环境应构建静态资源并由 Nginx/CDN 托管。