# Windows EXE 分发说明

`期权卖方算账神器.exe` 是本地只读账本程序。它启动后会自动在默认浏览器打开界面，无需安装 Node.js 或 Python。

## 给最终用户的使用方式

1. 安装并登录官方 Futu OpenD，确认它已在本机运行（默认端口 `11111`）。
2. 解压整个 `期权卖方算账神器` 文件夹；不要只复制其中的 EXE。
3. 双击 `期权卖方算账神器.exe`，浏览器将自动打开本地页面。
4. 在“连接设置”填写自己的账户尾号并同步。

每位用户的数据会保存于 `%LOCALAPPDATA%\Option Premium Ledger\ledger.sqlite3`，不会被写回安装文件夹，也不会包含在交付包中。程序不保存交易密码、不发单；OpenD 的登录、权限与账户选择由每位用户自行完成。

## 制作发布包

在开发机 PowerShell 运行：

```powershell
.\scripts\build-windows-exe.ps1 -Clean
```

将 `release-dist\期权卖方算账神器` 整个文件夹压缩后分发。该脚本会先构建前端，再用 PyInstaller 打包后端和富途 SDK。
