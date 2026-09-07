import { safeStorage } from "electron";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  renameSync,
  mkdirSync,
} from "node:fs";
import { join } from "node:path";
import type { Schema } from "../shared/bridge";

export type SavedCommand =
  | { kind: "create"; body: Schema["CreateProject"] }
  | { kind: "update"; project_id: string; body: Schema["UpdateProject"] };
type VaultState = {
  token: string | null;
  identity: Schema["Identity"] | null;
  pending: SavedCommand[];
};
export class Vault {
  private file: string;
  data: VaultState;
  constructor(directory: string) {
    mkdirSync(directory, { recursive: true });
    this.file = join(directory, "session.enc");
    if (
      !safeStorage.isEncryptionAvailable() ||
      (process.platform === "linux" &&
        safeStorage.getSelectedStorageBackend() === "basic_text")
    ) {
      throw new Error("系统凭据加密不可用。请启用操作系统密钥环后重试。");
    }
    this.data = existsSync(this.file)
      ? (JSON.parse(
          safeStorage.decryptString(readFileSync(this.file)),
        ) as VaultState)
      : { token: null, identity: null, pending: [] };
  }
  save() {
    const temp = `${this.file}.tmp`;
    writeFileSync(temp, safeStorage.encryptString(JSON.stringify(this.data)), {
      mode: 0o600,
    });
    renameSync(temp, this.file);
  }
  clear() {
    this.data = { token: null, identity: null, pending: [] };
    this.save();
  }
}
