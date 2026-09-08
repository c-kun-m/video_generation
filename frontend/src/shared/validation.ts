import Ajv2020 from "ajv/dist/2020";
import createSchema from "../../../contracts/schemas/CreateProject.json";
import updateSchema from "../../../contracts/schemas/UpdateProject.json";
import pairSchema from "../../../contracts/schemas/PairRequest.json";
import revisionSchema from "../../../contracts/schemas/SaveRevision.json";
import approvalSchema from "../../../contracts/schemas/SubmitApproval.json";
import startSchema from "../../../contracts/schemas/StartProductionRun.json";
import controlSchema from "../../../contracts/schemas/ControlProductionRun.json";
import type { Operation } from "./bridge";

const ajv = new Ajv2020({ allErrors: true, strict: false });
export const domainValidators = {
  CreateProject: ajv.compile(createSchema),
  UpdateProject: ajv.compile(updateSchema),
  PairRequest: ajv.compile(pairSchema),
  SaveRevision: ajv.compile(revisionSchema),
  SubmitApproval: ajv.compile(approvalSchema),
  StartProductionRun: ajv.compile(startSchema),
  ControlProductionRun: ajv.compile(controlSchema),
};
const id = {
  type: "string",
  pattern: "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
};
function object(properties: object, required: string[]) {
  return { type: "object", properties, required, additionalProperties: false };
}
function commandEnvelope(schema: object, reference = "project_id") {
  const { $defs, ...body } = schema as { $defs?: object };
  return ajv.compile({
    ...object({ [reference]: id, command: body }, [reference, "command"]),
    $defs,
  });
}
const contentKind = { type: "string", enum: ["brief", "script", "storyboard"] };
const draftKey = { project_id: id, entity_kind: contentKind };
const validators = {
  saveRevision: commandEnvelope(revisionSchema),
  submitApproval: commandEnvelope(approvalSchema),
  startRun: commandEnvelope(startSchema),
  controlRun: commandEnvelope(controlSchema, "run_id"),
  revisions: ajv.compile(
    object({ ...draftKey, before: { type: "integer", minimum: 1 } }, [
      "project_id",
      "entity_kind",
    ]),
  ),
  approvals: ajv.compile(
    object({ project_id: id, revision_id: id }, ["project_id"]),
  ),
  run: ajv.compile(object({ run_id: id }, ["run_id"])),
  command: ajv.compile(object({ command_id: id }, ["command_id"])),
  getDraft: ajv.compile(object(draftKey, ["project_id", "entity_kind"])),
  saveDraft: ajv.compile({
    ...object(
      {
        ...draftKey,
        base_row_version: { type: "integer", minimum: 0 },
        payload: revisionSchema.properties.payload,
        updated_at: { type: "string", maxLength: 80 },
      },
      [
        "project_id",
        "entity_kind",
        "base_row_version",
        "payload",
        "updated_at",
      ],
    ),
    $defs: revisionSchema.$defs,
  }),
  deleteDraft: ajv.compile(
    object({ ...draftKey, updated_at: { type: "string", maxLength: 80 } }, [
      "project_id",
      "entity_kind",
      "updated_at",
    ]),
  ),

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
const noArgs = new Set([
  "state",
  "health",
  "me",
  "logout",
  "capabilities",
  "executionStatus",
]);
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
