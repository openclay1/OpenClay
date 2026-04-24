'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('clayApp', {
  /** Open a URL in the OS default browser (not in Electron). */
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  /** Returns the backend base URL (http://localhost:3000). */
  backendUrl: () => ipcRenderer.invoke('backend-url'),
  /** Platform info for OS-specific UI tweaks. */
  platform: process.platform,
});
