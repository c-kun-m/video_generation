import Ajv2020 from "ajv/dist/2020";
import createSchema from "../../../contracts/schemas/CreateProject.json";
import updateSchema from "../../../contracts/schemas/UpdateProject.json";
import pairSchema from "../../../contracts/schemas/PairRequest.json";
import type { Operation } from "./bridge";

const ajv = new Ajv2020({ allErrors: true, strict: false });
export const domainValidators = {
  CreateProject: ajv.compile(createSchema),
  UpdateProject: ajv.compile(updateSchema),
  PairRequest: ajv.compile(pairSchema),
};
const id = {
  type: "string",
  pattern: "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
};
function object(properties: object, required: string[]) {
  return { type: "object", properties, required, additionalProperties: false };
}
const validators = {
  projects: ajv.compile(
    object(
      {
        archived: { type: "boolean" },
        cursor: { type: "string", maxLength: 512 },
      },
      ["archived"],
    ),
  ),
  snapshot: ajv.compile(object({ project_id: id }, ["project_id"])),
  events: ajv.compile(
    object({ project_id: id, after: { type: "integer", minimum: 0 } }, [
      "project_id",
      "after",
    ]),
  ),
  recover: ajv.compile(object({ command_id: id }, ["command_id"])),
  update: ajv.compile(
    object({ project_id: id, command: updateSchema }, [
      "project_id",
      "command",
    ]),
  ),
  create: domainValidators.CreateProject,
  pair: domainValidators.PairRequest,
};
const noArgs = new Set(["state", "health", "me", "logout", "capabilities"]);
export function validInput(
  operation: string,
  input: unknown,
): operation is Operation {
  if (noArgs.has(operation)) return input === undefined;
  if (!Object.hasOwn(validators, operation)) return false;
  const validator = validators[operation as keyof typeof validators];
  return typeof validator === "function" && validator(input);
}

export function localServiceUrl(value: string): string {
  const url = new URL(value);
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  )
    throw new Error("服务地址必须是 http://127.0.0.1:端口");
  return url.origin;
}
