import type { components } from "./api.generated";

export type Schema = components["schemas"];
export type Project = Schema["Project"];
export type Fault = Schema["ErrorDetail"];
export type Reply<T> = { ok: true; data: T } | { ok: false; error: Fault };
export type Pending = { command_id: string; label: string };
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
}
export type Operation = keyof VideoBridge;
declare global {
  interface Window {
    video: VideoBridge;
  }
}
