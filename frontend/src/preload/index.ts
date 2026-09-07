import { contextBridge, ipcRenderer } from "electron";
import type { VideoBridge } from "../shared/bridge";

// The renderer receives named domain methods, never ipcRenderer or arbitrary fetch.
const bridge: VideoBridge = {
  state: () => ipcRenderer.invoke("video:invoke", "state"),
  health: () => ipcRenderer.invoke("video:invoke", "health"),
  pair: (input) => ipcRenderer.invoke("video:invoke", "pair", input),
  me: () => ipcRenderer.invoke("video:invoke", "me"),
  logout: () => ipcRenderer.invoke("video:invoke", "logout"),
  capabilities: () => ipcRenderer.invoke("video:invoke", "capabilities"),
  projects: (input) => ipcRenderer.invoke("video:invoke", "projects", input),
  snapshot: (input) => ipcRenderer.invoke("video:invoke", "snapshot", input),
  events: (input) => ipcRenderer.invoke("video:invoke", "events", input),
  create: (input) => ipcRenderer.invoke("video:invoke", "create", input),
  update: (input) => ipcRenderer.invoke("video:invoke", "update", input),
  recover: (input) => ipcRenderer.invoke("video:invoke", "recover", input),
};
contextBridge.exposeInMainWorld("video", bridge);
