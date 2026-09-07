import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
} from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  mkdirSync,
  openSync,
  closeSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { parseEnv } from "node:util";
import { once } from "node:events";

const root = resolve(__dirname, "../../..");
const python = join(
  root,
  process.platform === "win32"
    ? "backend/.venv/Scripts/python.exe"
    : "backend/.venv/bin/python",
);
const configured = parseEnv(readFileSync(join(root, ".env"), "utf8"));
if (!configured.VIDEO_DATABASE_URL) throw new Error("Run setup first");
const original = new URL(
  configured.VIDEO_DATABASE_URL.replace("postgresql+psycopg:", "postgresql:"),
);
const database =
  configured.VIDEO_TEST_DATABASE_URL ??
  configured.VIDEO_DATABASE_URL.replace(/\/[^/]+$/, "/video_generation_test");
const testUrl = new URL(database.replace("postgresql+psycopg:", "postgresql:"));
if (
  !testUrl.pathname.endsWith("_test") ||
  testUrl.pathname === original.pathname
)
  throw new Error("E2E requires a separate _test database");
const env: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(process.env).filter(
      (entry): entry is [string, string] => entry[1] !== undefined,
    ),
  ),
  VIDEO_DATABASE_URL: database,
  VIDEO_API_PORT: "18000",
  VIDEO_SERVICE_URL: "http://127.0.0.1:18000",
  PYTHONIOENCODING: "utf-8",
};
delete env.ELECTRON_RUN_AS_NODE;
delete env.ELECTRON_RENDERER_URL;
mkdirSync(join(root, "runtime/verification"), { recursive: true });
const profile = mkdtempSync(join(root, "runtime/verification/desktop-"));
env.VIDEO_DESKTOP_DATA_DIR = profile;
let api: ChildProcess;
let desktop: ElectronApplication | undefined;
async function startApi() {
  const log = openSync(join(root, "runtime/verification/e2e-api.log"), "a");
  api = spawn(
    python,
    ["-c", "from video_generation.cli import serve; serve()"],
    { cwd: root, env, windowsHide: true, stdio: ["ignore", log, log] },
  );
  closeSync(log);
  await expect
    .poll(async () => {
      try {
        return (await fetch(env.VIDEO_SERVICE_URL + "/health/ready")).status;
      } catch {
        return 0;
      }
    })
    .toBe(200);
}
async function stopApi() {
  if (api?.exitCode === null) {
    const exited = once(api, "exit");
    api.kill();
    await exited;
  }
}
async function launch() {
  desktop = await electron.launch({
    ...(process.env.VIDEO_DESKTOP_EXECUTABLE
      ? { executablePath: process.env.VIDEO_DESKTOP_EXECUTABLE, args: [] }
      : { args: [join(root, "frontend/out/main/index.js")] }),
    cwd: join(root, "frontend"),
    env,
  });
  const page = await desktop.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  return page;
}
test.afterAll(async () => {
  await desktop?.close();
  await stopApi();
});
test("real desktop: pairing, CRUD, safe bridge, recovery, conflict and process restart", async () => {
  await startApi();
  const invitation = spawnSync(
    python,
    [
      "-c",
      "from video_generation.cli import main; main()",
      "init-owner",
      "--json",
    ],
    { cwd: root, env, encoding: "utf8", windowsHide: true },
  );
  expect(invitation.status).toBe(0);
  let page = await launch();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page
    .getByLabel("一次性配对码")
    .fill(JSON.parse(invitation.stdout).pairing_code);
  await page.getByRole("button", { name: "连接工作空间" }).click();
  await expect(page.getByRole("heading", { name: "项目库." })).toBeVisible();
  const bridge = await page.evaluate(async () => ({
    state: await window.video.state(),
    require: typeof (window as unknown as { require: unknown }).require,
    invalid: await window.video.create({
      command_id: "bad",
      title: "invalid",
      tenant_id: "injected",
    } as never),
  }));
  expect(bridge.require).toBe("undefined");
  expect(JSON.stringify(bridge.state)).not.toContain("access_token");
  expect(bridge.invalid.ok).toBe(false);
  const security = await desktop!.evaluate(({ app, BrowserWindow }) => {
    const processId =
      BrowserWindow.getAllWindows()[0].webContents.getOSProcessId();
    return app.getAppMetrics().find((metric) => metric.pid === processId)
      ?.sandboxed;
  });
  expect(security).toBe(true);
  const forged = await desktop!.evaluate(async ({ BrowserWindow }) => {
    const foreign = new BrowserWindow({
      show: false,
      webPreferences: { nodeIntegration: true, contextIsolation: false },
    });
    try {
      await foreign.loadURL("about:blank");
      return await foreign.webContents.executeJavaScript(
        "require('electron').ipcRenderer.invoke('video:invoke', 'state')",
      );
    } finally {
      foreign.destroy();
    }
  });
  expect(forged.ok).toBe(false);
  expect(forged.error.code).toBe("FORBIDDEN");
  const name = `雨后的杭州 · ${Date.now()}`;
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill(name);
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const id = new URL(page.url()).hash.split("/").pop()!;
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  await page.getByLabel("项目名称").fill(name + " · 完整版");
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(
    page.getByRole("heading", { name: name + " · 完整版", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "归档", exact: true }).click();
  await expect(page.getByRole("button", { name: "恢复项目" })).toBeVisible();
  await page.getByRole("button", { name: "恢复项目" }).click();
  await expect(
    page.getByRole("button", { name: "归档", exact: true }),
  ).toBeVisible();
  // A second command updates the server while a rename dialog holds an older version.
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  await page.getByLabel("项目名称").fill(name + " · 我的修改");
  await page.evaluate(async (project_id) => {
    const snapshot = await window.video.snapshot({ project_id });
    if (!snapshot.ok) throw new Error("snapshot failed");
    await window.video.update({
      project_id,
      command: {
        command_id: crypto.randomUUID(),
        expected_row_version: snapshot.data.project.row_version,
        title: "另一个窗口的修改",
      },
    });
  }, id);
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(page.getByText("当前已保存：另一个窗口的修改")).toBeVisible();
  await page.getByRole("button", { name: "以最新版本为基础继续编辑" }).click();
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(
    page.getByRole("heading", { name: name + " · 我的修改", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: join(root, "runtime/verification/project-detail.png"),
  });
  await page.getByRole("link", { name: "返回项目库" }).click();
  // Lose the response only after the real database committed. Main must retain the original command.
  await desktop!.evaluate(() => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (...args) => {
      const response = await originalFetch(...args);
      const request = args[0] as Request;
      if (
        request.method === "POST" &&
        request.url.endsWith("/video/v1/projects")
      ) {
        globalThis.fetch = originalFetch;
        throw new Error("Simulated lost response after commit");
      }
      return response;
    };
  });
  const recoveryName = `断线恢复项目 · ${Date.now()}`;
  const outcome = await page.evaluate(
    (title) => window.video.create({ command_id: crypto.randomUUID(), title }),
    recoveryName,
  );
  expect(outcome.ok).toBe(false);
  const pending = await page.evaluate(() => window.video.state());
  expect(pending.ok && pending.data.pending.length).toBe(1);
  await desktop!.close();
  desktop = undefined;
  await stopApi();
  page = await launch();
  await expect(page.getByText("服务离线", { exact: true })).toBeVisible();
  await startApi();
  await expect(page.getByText("本机服务在线", { exact: true })).toBeVisible();
  await expect
    .poll(async () => {
      const state = await page.evaluate(() => window.video.state());
      return state.ok ? state.data.pending.length : -1;
    })
    .toBe(0);
  const recovered = await page.evaluate(
    (title) =>
      window.video
        .projects({ archived: false })
        .then((result) =>
          result.ok
            ? result.data.items.filter((project) => project.title === title)
                .length
            : -1,
        ),
    recoveryName,
  );
  expect(recovered).toBe(1);
  await expect(
    page.getByRole("heading", { name: name + " · 我的修改", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: join(root, "runtime/verification/project-library.png"),
  });
  await page.getByRole("link", { name: "服务设置" }).click();
  await expect(
    page.getByText("ComfyUI 镜头生成", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("尚未接入", { exact: true })).toHaveCount(4);
  expect(errors).toEqual([]);
});
