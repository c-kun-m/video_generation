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
  executionStatus: () => ipcRenderer.invoke("video:invoke", "executionStatus"),
  projects: (input) => ipcRenderer.invoke("video:invoke", "projects", input),
  snapshot: (input) => ipcRenderer.invoke("video:invoke", "snapshot", input),
  events: (input) => ipcRenderer.invoke("video:invoke", "events", input),
  create: (input) => ipcRenderer.invoke("video:invoke", "create", input),
  update: (input) => ipcRenderer.invoke("video:invoke", "update", input),
  recover: (input) => ipcRenderer.invoke("video:invoke", "recover", input),
  saveRevision: (input) =>
    ipcRenderer.invoke("video:invoke", "saveRevision", input),
  submitApproval: (input) =>
    ipcRenderer.invoke("video:invoke", "submitApproval", input),
  startRun: (input) => ipcRenderer.invoke("video:invoke", "startRun", input),
  controlRun: (input) =>
    ipcRenderer.invoke("video:invoke", "controlRun", input),
  revisions: (input) => ipcRenderer.invoke("video:invoke", "revisions", input),
  approvals: (input) => ipcRenderer.invoke("video:invoke", "approvals", input),
  run: (input) => ipcRenderer.invoke("video:invoke", "run", input),
  command: (input) => ipcRenderer.invoke("video:invoke", "command", input),
  getDraft: (input) => ipcRenderer.invoke("video:invoke", "getDraft", input),
  saveDraft: (input) => ipcRenderer.invoke("video:invoke", "saveDraft", input),
  deleteDraft: (input) =>
    ipcRenderer.invoke("video:invoke", "deleteDraft", input),
};
contextBridge.exposeInMainWorld("video", bridge);
