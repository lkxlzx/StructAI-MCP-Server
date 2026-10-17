/* 渲染进程桥：仅暴露窗口控制，前端据此判断处于桌面壳环境 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('midasDesktop', {
  platform: process.platform,
  version: process.versions.electron,
  minimize: () => ipcRenderer.send('win:minimize'),
  toggleMaximize: () => ipcRenderer.send('win:toggle-maximize'),
  close: () => ipcRenderer.send('win:close'),
  isMaximized: () => ipcRenderer.invoke('win:is-maximized')
});
