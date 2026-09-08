import type { components } from "./api.generated";

export type Schema = components["schemas"];
export type Project = Schema["Project"];
export type Fault = Schema["ErrorDetail"];
export type Reply<T> = { ok: true; data: T } | { ok: false; error: Fault };
export type Pending = { command_id: string; label: string };
export type ContentKind = "brief" | "script" | "storyboard";
export interface LocalDraft {
  project_id: string;
  entity_kind: ContentKind;
  base_row_version: number;
  payload: Schema["SaveRevision"]["payload"];
  updated_at: string;
}
export interface DesktopState {
  service_url: string;
  paired: boolean;
  identity: Schema["Identity"] | null;
  pending: Pending[];
  version: string;
}
export interface VideoBridge {
  state(): Promise<Reply<DesktopState>>;
  health(): Promise<Reply<Schema["Health"]>>;
  pair(input: Schema["PairRequest"]): Promise<Reply<Schema["Identity"]>>;
  me(): Promise<Reply<Schema["Identity"]>>;
  logout(): Promise<Reply<Schema["LogoutResponse"]>>;
  capabilities(): Promise<Reply<Schema["Capabilities"]>>;
  executionStatus(): Promise<Reply<Schema["OutboxStatus"]>>;
  projects(input: {
    archived: boolean;
    cursor?: string;
  }): Promise<Reply<Schema["ProjectPage"]>>;
  snapshot(input: {
    project_id: string;
  }): Promise<Reply<Schema["ProjectSnapshot"]>>;
  events(input: {
    project_id: string;
    after: number;
  }): Promise<Reply<Schema["EventPage"]>>;
  create(
    input: Schema["CreateProject"],
  ): Promise<Reply<Schema["CommandResult"]>>;
  update(input: {
    project_id: string;
    command: Schema["UpdateProject"];
  }): Promise<Reply<Schema["CommandResult"]>>;
  recover(input: {
    command_id: string;
  }): Promise<Reply<Schema["CommandResult"]>>;
  saveRevision(input: {
    project_id: string;
    command: Schema["SaveRevision"];
  }): Promise<Reply<Schema["CommandResult"]>>;
  submitApproval(input: {
    project_id: string;
    command: Schema["SubmitApproval"];
  }): Promise<Reply<Schema["CommandResult"]>>;
  startRun(input: {
    project_id: string;
    command: Schema["StartProductionRun"];
  }): Promise<Reply<Schema["CommandResult"]>>;
  controlRun(input: {
    run_id: string;
    command: Schema["ControlProductionRun"];
  }): Promise<Reply<Schema["CommandResult"]>>;
  revisions(input: {
    project_id: string;
    entity_kind: ContentKind;
    before?: number;
  }): Promise<Reply<Schema["RevisionPage"]>>;
  approvals(input: {
    project_id: string;
    revision_id?: string;
  }): Promise<Reply<Schema["ApprovalPage"]>>;
  run(input: { run_id: string }): Promise<Reply<Schema["ProductionRunDetail"]>>;
  command(input: {
    command_id: string;
  }): Promise<Reply<Schema["CommandResult"]>>;
  getDraft(input: {
    project_id: string;
    entity_kind: ContentKind;
  }): Promise<Reply<LocalDraft | null>>;
  saveDraft(input: LocalDraft): Promise<Reply<LocalDraft>>;
  deleteDraft(input: {
    project_id: string;
    entity_kind: ContentKind;
    updated_at: string;
  }): Promise<Reply<{ deleted: boolean }>>;
}
export type Operation = keyof VideoBridge;
declare global {
  interface Window {
    video: VideoBridge;
  }
}
