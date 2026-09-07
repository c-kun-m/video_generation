import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  net,
  protocol,
  session,
} from "electron";
import { join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { localServiceUrl, validInput } from "../shared/validation";
import { Service, ServiceError, fault } from "./service";
import { Vault } from "./vault";

protocol.registerSchemesAsPrivileged([
  {
    scheme: "app",
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  },
]);
if (process.env.VIDEO_DESKTOP_DATA_DIR)
  app.setPath("userData", resolve(process.env.VIDEO_DESKTOP_DATA_DIR));
const ownsLock = app.requestSingleInstanceLock();
if (!ownsLock) app.quit();
else
  app
    .whenReady()
    .then(async () => {
      const devUrl = process.env.ELECTRON_RENDERER_URL;
      if (devUrl && devUrl !== "http://127.0.0.1:5173")
        throw new Error("开发页面地址不在白名单中。");
      const root = resolve(__dirname, "../renderer");
      protocol.handle("app", (request) => {
        const url = new URL(request.url);
        if (url.hostname !== "video" || request.method !== "GET")
          return new Response(null, { status: 403 });
        let file: string;
        try {
          file = resolve(
            root,
            "." +
              decodeURIComponent(
                url.pathname === "/" ? "/index.html" : url.pathname,
              ),
          );
        } catch {
          return new Response(null, { status: 400 });
        }
        if (!file.startsWith(root + sep))
          return new Response(null, { status: 403 });
        return net.fetch(pathToFileURL(file).toString());
      });
      session.defaultSession.setPermissionRequestHandler(
        (_webContents, _permission, callback) => callback(false),
      );
      session.defaultSession.setPermissionCheckHandler(() => false);
      session.defaultSession.webRequest.onHeadersReceived(
        (details, callback) => {
          const csp = `default-src 'self'; script-src 'self'${devUrl ? " 'unsafe-inline'" : ""}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src ${devUrl ? "http://127.0.0.1:5173 ws://127.0.0.1:5173" : "'none'"}; object-src 'none'; base-uri 'none'; frame-src 'none'; form-action 'none'`;
          callback({
            responseHeaders: {
              ...details.responseHeaders,
              "Content-Security-Policy": [csp],
            },
          });
        },
      );
      const service = new Service(
        localServiceUrl(
          process.env.VIDEO_SERVICE_URL ?? "http://127.0.0.1:8000",
        ),
        new Vault(app.getPath("userData")),
        app.getVersion(),
      );
      const window = new BrowserWindow({
        width: 1360,
        height: 900,
        minWidth: 1024,
        minHeight: 720,
        backgroundColor: "#0c1016",
        title: "Video Generation",
        autoHideMenuBar: true,
        webPreferences: {
          preload: join(__dirname, "../preload/index.js"),
          sandbox: true,
          contextIsolation: true,
          nodeIntegration: false,
          webSecurity: true,
        },
      });
      app.on("second-instance", () => {
        if (window.isMinimized()) window.restore();
        window.focus();
      });
      window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      window.webContents.on("will-navigate", (event) => event.preventDefault());
      window.webContents.on("will-attach-webview", (event) =>
        event.preventDefault(),
      );
      ipcMain.handle(
        "video:invoke",
        async (event, operation: unknown, input: unknown) => {
          const sender = event.senderFrame;
          const origin = sender?.url.split("#")[0];
          if (
            event.sender !== window.webContents ||
            sender !== window.webContents.mainFrame ||
            !(devUrl
              ? origin === `${devUrl}/`
              : origin === "app://video/index.html")
          ) {
            return {
              ok: false,
              error: fault("FORBIDDEN", "调用来源不受信任。"),
            };
          }
          if (typeof operation !== "string" || !validInput(operation, input))
            return {
              ok: false,
              error: fault("VALIDATION_FAILED", "请求参数不符合接口合同。"),
            };
          try {
            return { ok: true, data: await service.dispatch(operation, input) };
          } catch (error) {
            return {
              ok: false,
              error:
                error instanceof ServiceError
                  ? error.fault
                  : fault(
                      "DESKTOP_ERROR",
                      "本机操作未完成，请检查桌面数据目录权限。",
                    ),
            };
          }
        },
      );
      await window.loadURL(devUrl ? `${devUrl}/` : "app://video/index.html");
    })
    .catch((error) => {
      dialog.showErrorBox(
        "桌面启动失败",
        error instanceof Error ? error.message : "未知错误",
      );
      app.quit();
    });
app.on("window-all-closed", () => app.quit());
