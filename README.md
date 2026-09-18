# 期权卖方算账神器

一个本地优先的富途 OpenD 美股期权卖方账本工具，用于复盘 Sell Put、Covered Call 与买回平仓的收益。它只读连接用户本机 OpenD，不会下单、不保存交易密码，也不会上传交易数据。

> 完全单机运行

> 适合希望把卖方期权交易，比如卖covered call，卖put的收益清晰核算的富途用户。

## 功能

- **卖方收益核算**：仅将 `SELL_SHORT` 视为卖方开仓、`BUY_BACK` 视为平仓；买方期权和正股交易不会混入收益。
- **FIFO 配对**：按合约和时间顺序配对卖出与买回，展示已实现毛利润、费用和净利润。
- **持仓追踪**：展示未平仓 Sell Put / Sell Call 的权利金、买回估值、浮盈亏、持有天数及 DTE。
- **到期击穿概率**：结合标的价格、IV、行权价与剩余期限计算价内概率；盘中用实时价，非盘中用前收盘价。
- **正股持仓检查表**：读取美股正股持仓，标记是否已有 Covered Call 或 Sell Put，便于每周检查。
- **时间筛选与归因**：支持今天、本周、本月、上月与自定义日期；已实现收益按平仓日归属。
- **按标的复盘**：展示已实现净盈利、持仓、买回估值、权利金流入、胜率及盈亏横向比较。
- **CSV 导出**：导出当前账本视图。
- **安全防误用**：账户尾号匹配失败即停止同步；没有真实、已验证数据时显示空状态，不使用演示数据。

- ## 功能截图（数据是测试数据）
- 
<img width="1121" height="698" alt="image" src="https://github.com/user-attachments/assets/4aa8d111-12f4-4e9c-a038-dc8b886308db" />



## 数据与隐私

- 数据只保存在用户本机 SQLite 数据库。
- 只调用 OpenD 的读取接口：账户、历史成交、订单费用、期权行情和正股持仓。
- 不调用交易解锁或下单接口，也不保存交易密码。
- 到期击穿概率是基于 IV 的风险估计，不是投资建议或收益保证。

## 使用前提

1. Windows 10/11。
2. 已安装、登录官方 Futu OpenD / moomoo OpenD，并开启 API 服务（默认 `127.0.0.1:11111`）。
3. 当前账户具有对应的美股交易与行情权限。

## 使用发布版

1. 解压完整发布目录，不要只复制 EXE。
2. 双击 `期权卖方算账神器.exe`。
3. 在默认浏览器打开的本地页面中填写 OpenD 地址、端口、券商和自己的账户尾号。
4. 点击“立即同步”。

## 本地开发

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 终端 1
.\.venv\Scripts\python.exe backend\server.py

# 终端 2
npm run dev
```

开发前端默认访问 `http://localhost:4173/`；本地 API 为 `http://127.0.0.1:8765/`。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_ledger
npm run build
.\scripts\build-windows-exe.ps1 -Clean
```

构建脚本会生成 `release-dist\期权卖方算账神器\期权卖方算账神器.exe`。数据库、OpenD 日志、发布包、虚拟环境和构建缓存均被 `.gitignore` 排除。

## 项目结构

```text
src/                 React 前端
backend/             OpenD 读取适配器、FIFO 账本、SQLite API
scripts/             Windows 打包和发布脚本
tests/               前端构建相关测试
```

## 免责声明

本项目仅用于个人交易记录与数据复盘，不构成投资、税务或法律建议。使用者应自行核对成交、费用、账户权限与风险，并对交易决策负责。

欢迎关注我是NG哥公众号，一起畅游美股。

<img width="510" height="326" alt="image" src="https://github.com/user-attachments/assets/490f196c-dea1-4464-aa8d-8355afc8adea" />


## 贡献

欢迎通过 Issue 或 Pull Request 报告问题、完善核算逻辑、补充测试或优化界面。请勿提交账户数据、SQLite 数据库、OpenD 日志或发布压缩包。
