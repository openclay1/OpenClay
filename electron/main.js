'use strict';

const { app, BrowserWindow, shell, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const net = require('net');

const BACKEND_PORT = 8100;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const isDev = process.env.NODE_ENV === 'development';

let mainWindow = null;
let backendProc = null;

// ── Backend startup ──────────────────────────────────────────────

function findPython() {
  const candidates = ['python3', 'python', '/usr/local/bin/python3', '/opt/homebrew/bin/python3'];
  for (const p of candidates) {
    try {
      const r = require('child_process').spawnSync(p, ['--version'], { timeout: 2000 });
      if (r.status === 0) return p;
    } catch {}
  }
  return 'python3';
}

function startBackend() {
  // Points at claycode/clay_server.py — one level up from electron/ within the claycode repo
  const serverPath = path.join(__dirname, '..', 'clay_server.py');
  const cwd = path.join(__dirname, '..');  // claycode repo root
  const python = findPython();

  backendProc = spawn(python, [serverPath], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1', PORT: String(BACKEND_PORT) },
    detached: false,
  });

  backendProc.stdout.on('data', d => process.stdout.write('[clay] ' + d));
  backendProc.stderr.on('data', d => process.stderr.write('[clay] ' + d));
  backendProc.on('exit', code => {
    console.log(`[clay] backend exited (${code})`);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.executeJavaScript(
        `document.title = 'ClayCode — backend stopped'`
      ).catch(() => {});
    }
  });
}

// ── Port-ready check ─────────────────────────────────────────────

function isPortOpen(port) {
  return new Promise(resolve => {
    const s = net.createConnection(port, '127.0.0.1');
    s.on('connect', () => { s.destroy(); resolve(true); });
    s.on('error', () => { s.destroy(); resolve(false); });
    s.setTimeout(400, () => { s.destroy(); resolve(false); });
  });
}

async function waitForBackend(maxMs = 15000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (await isPortOpen(BACKEND_PORT)) return true;
    await new Promise(r => setTimeout(r, 300));
  }
  return false;
}

// ── Window management ────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 800,
    minWidth: 720,
    minHeight: 500,
    backgroundColor: '#161310',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // Load loading screen immediately (file://) — no backend needed
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));

  if (isDev) mainWindow.webContents.openDevTools();

  // Open external links (project URLs) in the OS browser, not Electron
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(BACKEND_URL) && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
}

// ── IPC ──────────────────────────────────────────────────────────

ipcMain.handle('open-external', (_, url) => shell.openExternal(url));
ipcMain.handle('backend-url', () => BACKEND_URL);

// ── App lifecycle ────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend();
  createWindow();

  const ready = await waitForBackend(15000);
  if (!mainWindow || mainWindow.isDestroyed()) return;

  if (ready) {
    mainWindow.loadURL(BACKEND_URL);
  } else {
    // Backend didn't start — show error in loading page
    mainWindow.webContents.executeJavaScript(`
      document.getElementById('status').textContent =
        'Backend failed to start. Make sure Python 3 is installed.';
      document.getElementById('status').style.color = '#e06438';
      document.getElementById('spinner').style.display = 'none';
    `).catch(() => {});
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backendProc) { try { backendProc.kill(); } catch {} }
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProc) { try { backendProc.kill(); } catch {} }
});
