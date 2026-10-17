/* MIDAS MCP 管理器 · Windows 桌面版主进程
   - 无边框窗口 + 自绘标题栏（与 Web 版同一份 UI，仅多出窗口按钮）
   - 默认窗口尺寸 1536x1024（与设计稿一致）
   - 载入 web/index.html（打包后位于 resources/app/web，开发时位于仓库 ../web）*/
const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

const DESIGN_WIDTH = 1536;
const DESIGN_HEIGHT = 1024;

function webEntry() {
  const packaged = path.join(__dirname, 'web', 'index.html');
  const dev = path.join(__dirname, '..', 'web', 'index.html');
  if (fs.existsSync(packaged)) return packaged;
  if (fs.existsSync(dev)) return dev;
  throw new Error('未找到 web/index.html');
}

let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: DESIGN_WIDTH,
    height: DESIGN_HEIGHT,
    minWidth: 1320,
    minHeight: 720,
    show: false,
    frame: false,
    backgroundColor: '#F2F6FB',
    title: 'MIDAS MCP 管理器',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false
    }
  });

  win.setMenuBarVisibility(false);
  win.loadFile(webEntry());
  win.once('ready-to-show', () => win.show());

  // 最大化状态广播（供后续 UI 使用）
  const notify = () => win && win.webContents.send('win:state', { maximized: win.isMaximized() });
  win.on('maximize', notify);
  win.on('unmaximize', notify);

  // 外链走系统浏览器
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
}

ipcMain.on('win:minimize', () => win && win.minimize());
ipcMain.on('win:toggle-maximize', () => {
  if (!win) return;
  if (win.isMaximized()) win.unmaximize();
  else win.maximize();
});
ipcMain.on('win:close', () => win && win.close());
ipcMain.handle('win:is-maximized', () => (win ? win.isMaximized() : false));

const single = app.requestSingleInstanceLock();
if (!single) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
}
