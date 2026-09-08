import createClient from "openapi-fetch";
import type { paths } from "../shared/api.generated";
import type {
  Fault,
  Schema,
  Operation,
  LocalDraft,
  ContentKind,
} from "../shared/bridge";
import { Vault, type SavedCommand } from "./vault";

export class ServiceError extends Error {
  constructor(
    public fault: Fault,
    public status = 0,
  ) {
    super(fault.message);
  }
}
export function fault(code: string, message: string): Fault {
  return { code, message, trace_id: "", fields: [], current_row_version: null };
}
export class Service {
  private client;
  private mutating = false;
  constructor(
    public url: string,
    public vault: Vault,
    private version: string,
  ) {
    this.client = createClient<paths>({
      baseUrl: url,
      fetch: async (request) => {
        if (vault.data.token)
          request.headers.set("Authorization", `Bearer ${vault.data.token}`);
        try {
          return await fetch(request, {
            signal: AbortSignal.timeout(8000),
            redirect: "error",
          });
        } catch {
          throw new ServiceError(
            fault("OFFLINE", "无法连接本机服务。请检查后端是否启动。"),
          );
        }
      },
    });
  }
  private async unwrap<T>(
    response: Promise<{ data?: T; error?: unknown; response: Response }>,
  ): Promise<T> {
    const result = await response;
    if (result.error || !result.response.ok) {
      const error = result.error as { error?: Fault };
      throw new ServiceError(
        error?.error ?? fault("SERVICE_ERROR", "服务返回异常，请稍后重试。"),
        result.response.status,
      );
    }
    return result.data as T;
  }
  private requireSession() {
    if (!this.vault.data.token)
      throw new ServiceError(
        fault("UNAUTHENTICATED", "请先配对本机设备。"),
        401,
      );
  }
  private async execute(
    command: SavedCommand,
  ): Promise<Schema["CommandResult"]> {
    try {
      let result: Schema["CommandResult"];
      switch (command.kind) {
        case "create":
          result = await this.unwrap(
            this.client.POST("/video/v1/projects", { body: command.body }),
          );
          break;
        case "update":
          result = await this.unwrap(
            this.client.PATCH("/video/v1/projects/{project_id}", {
              params: { path: { project_id: command.project_id } },
              body: command.body,
            }),
          );
          break;
        case "saveRevision":
          result = await this.unwrap(
            this.client.POST("/video/v1/projects/{project_id}/revisions", {
              params: { path: { project_id: command.project_id } },
              body: command.body,
            }),
          );
          break;
        case "submitApproval":
          result = await this.unwrap(
            this.client.POST("/video/v1/projects/{project_id}/approvals", {
              params: { path: { project_id: command.project_id } },
              body: command.body,
            }),
          );
          break;
        case "startRun":
          result = await this.unwrap(
            this.client.POST(
              "/video/v1/projects/{project_id}/production-runs",
              {
                params: { path: { project_id: command.project_id } },
                body: command.body,
              },
            ),
          );
          break;
        case "controlRun":
          result = await this.unwrap(
            this.client.POST("/video/v1/production-runs/{run_id}/commands", {
              params: { path: { run_id: command.run_id } },
              body: command.body,
            }),
          );
          break;
      }
      this.removePending(command.body.command_id);
      return result;
    } catch (error) {
      // 5xx / disconnect can occur after commit. Keep the original ID and payload for recovery.
      if (
        error instanceof ServiceError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 401
      )
        this.removePending(command.body.command_id);
      throw error;
    }
  }
  private removePending(id: string) {
    this.vault.data.pending = this.vault.data.pending.filter(
      (x) => x.body.command_id !== id,
    );
    this.vault.save();
  }
  private async write(command: SavedCommand) {
    this.requireSession();
    if (this.vault.data.pending.length)
      throw new ServiceError(
        fault("PENDING_COMMAND", "请先恢复待确认的操作，再进行新的修改。"),
      );
    this.vault.data.pending.push(command);
    this.vault.save();
    return this.execute(command);
  }
  async dispatch(operation: Operation, input: unknown): Promise<unknown> {
    const writes = [
      "pair",
      "logout",
      "create",
      "update",
      "recover",
      "saveRevision",
      "submitApproval",
      "startRun",
      "controlRun",
    ];
    if (!writes.includes(operation))
      return this.executeOperation(operation, input);
    if (this.mutating)
      throw new ServiceError(fault("BUSY", "另一项操作正在提交，请稍后重试。"));
    this.mutating = true;
    try {
      return await this.executeOperation(operation, input);
    } finally {
      this.mutating = false;
    }
  }
  private async executeOperation(
    operation: Operation,
    input: unknown,
  ): Promise<unknown> {
    // Input is validated against the generated schemas before reaching this switch.
    switch (operation) {
      case "state":
        return {
          service_url: this.url,
          paired: !!this.vault.data.token,
          identity: this.vault.data.identity,
          pending: (this.mutating ? [] : this.vault.data.pending).map((x) => ({
            command_id: x.body.command_id,
            label: {
              create: "创建项目",
              update: "修改项目",
              saveRevision: "保存内容",
              submitApproval: "审批版本",
              startRun: "启动演练",
              controlRun: "控制演练",
            }[x.kind],
          })),
          version: this.version,
        };
      case "health":
        return this.unwrap(this.client.GET("/health/ready"));
      case "pair": {
        if (this.vault.data.token) {
          let active = true;
          try {
            await this.unwrap(this.client.GET("/video/v1/me"));
          } catch (error) {
            if (error instanceof ServiceError && error.status === 401)
              active = false;
            else throw error;
          }
          if (active)
            throw new ServiceError(
              fault("ALREADY_PAIRED", "请先解除当前配对。"),
              409,
            );
        }
        const result = await this.unwrap(
          this.client.POST("/video/v1/auth/pair", {
            body: input as Schema["PairRequest"],
          }),
        );
        const old = this.vault.data;
        if (
          old.pending.length &&
          (old.identity?.actor_id !== result.identity.actor_id ||
            old.identity?.tenant_id !== result.identity.tenant_id)
        ) {
          throw new ServiceError(
            fault(
              "IDENTITY_MISMATCH",
              "待确认操作属于另一个身份，请使用原工作空间身份配对。",
            ),
          );
        }
        this.vault.data = {
          token: result.access_token,
          identity: result.identity,
          pending: old.pending,
          drafts: old.drafts ?? {},
        };
        this.vault.save();
        return result.identity;
      }
      case "logout": {
        if (this.vault.data.pending.length)
          throw new ServiceError(
            fault("PENDING_COMMAND", "请先恢复待确认的操作，再解除配对。"),
          );
        try {
          await this.unwrap(this.client.POST("/video/v1/auth/logout"));
        } catch (error) {
          if (!(error instanceof ServiceError && error.status === 401))
            throw error;
        }
        this.vault.clear();
        return { revoked: true };
      }
      case "me":
        return this.unwrap(this.client.GET("/video/v1/me"));
      case "capabilities":
        return this.unwrap(this.client.GET("/video/v1/system/capabilities"));
      case "executionStatus":
        return this.unwrap(
          this.client.GET("/video/v1/system/execution-status"),
        );
      case "projects":
        return this.unwrap(
          this.client.GET("/video/v1/projects", {
            params: { query: input as { archived: boolean; cursor?: string } },
          }),
        );
      case "snapshot":
        return this.unwrap(
          this.client.GET("/video/v1/projects/{project_id}/snapshot", {
            params: { path: input as { project_id: string } },
          }),
        );
      case "events": {
        const { project_id, after } = input as {
          project_id: string;
          after: number;
        };
        return this.unwrap(
          this.client.GET("/video/v1/projects/{project_id}/events", {
            params: { path: { project_id }, query: { after } },
          }),
        );
      }
      case "create":
        return this.write({
          kind: "create",
          body: input as Schema["CreateProject"],
        });
      case "update": {
        const { project_id, command } = input as {
          project_id: string;
          command: Schema["UpdateProject"];
        };
        return this.write({ kind: "update", project_id, body: command });
      }
      case "saveRevision": {
        const { project_id, command } = input as {
          project_id: string;
          command: Schema["SaveRevision"];
        };
        return this.write({ kind: "saveRevision", project_id, body: command });
      }
      case "submitApproval": {
        const { project_id, command } = input as {
          project_id: string;
          command: Schema["SubmitApproval"];
        };
        return this.write({
          kind: "submitApproval",
          project_id,
          body: command,
        });
      }
      case "startRun": {
        const { project_id, command } = input as {
          project_id: string;
          command: Schema["StartProductionRun"];
        };
        return this.write({ kind: "startRun", project_id, body: command });
      }
      case "controlRun": {
        const { run_id, command } = input as {
          run_id: string;
          command: Schema["ControlProductionRun"];
        };
        return this.write({ kind: "controlRun", run_id, body: command });
      }
      case "revisions": {
        const { project_id, ...query } = input as {
          project_id: string;
          entity_kind: ContentKind;
          before?: number;
        };
        return this.unwrap(
          this.client.GET("/video/v1/projects/{project_id}/revisions", {
            params: { path: { project_id }, query },
          }),
        );
      }
      case "approvals": {
        const { project_id, ...query } = input as {
          project_id: string;
          revision_id?: string;
        };
        return this.unwrap(
          this.client.GET("/video/v1/projects/{project_id}/approvals", {
            params: { path: { project_id }, query },
          }),
        );
      }
      case "run":
        return this.unwrap(
          this.client.GET("/video/v1/production-runs/{run_id}", {
            params: { path: input as { run_id: string } },
          }),
        );
      case "command":
        return this.unwrap(
          this.client.GET("/video/v1/commands/{command_id}", {
            params: { path: input as { command_id: string } },
          }),
        );
      case "getDraft":
      case "saveDraft":
      case "deleteDraft": {
        this.requireSession();
        const identity = this.vault.data.identity;
        if (!identity)
          throw new ServiceError(
            fault("UNAUTHENTICATED", "请先配对本机设备。"),
          );
        const draft = input as LocalDraft;
        const key = [
          identity.tenant_id,
          identity.actor_id,
          draft.project_id,
          draft.entity_kind,
        ].join("/");
        const drafts = (this.vault.data.drafts ??= {});
        if (operation === "getDraft") return drafts[key] ?? null;
        if (operation === "saveDraft") {
          if (draft.payload.kind !== draft.entity_kind)
            throw new ServiceError(
              fault("VALIDATION_FAILED", "草稿类型不匹配。"),
            );
          drafts[key] = draft;
          this.vault.save();
          return draft;
        }
        const matches = drafts[key]?.updated_at === draft.updated_at;
        if (matches) {
          delete drafts[key];
          this.vault.save();
        }
        return { deleted: matches };
      }
      case "recover": {
        this.requireSession();
        const { command_id } = input as { command_id: string };
        const pending = this.vault.data.pending.find(
          (x) => x.body.command_id === command_id,
        );
        if (!pending)
          throw new ServiceError(
            fault("NOT_FOUND", "没有这条待确认操作。"),
            404,
          );
        let result: Schema["CommandResult"];
        try {
          result = await this.unwrap(
            this.client.GET("/video/v1/commands/{command_id}", {
              params: { path: { command_id } },
            }),
          );
        } catch (error) {
          if (error instanceof ServiceError && error.status === 404)
            return this.execute(pending);
          throw error;
        }
        this.removePending(command_id);
        if (result.status === "REJECTED")
          throw new ServiceError(
            result.error ?? fault("REJECTED", "操作被拒绝。"),
            409,
          );
        return result;
      }
    }
  }
}
