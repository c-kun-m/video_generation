import { describe, expect, it } from "vitest";
import samples from "../../contracts/samples.json";
import {
  domainValidators,
  localServiceUrl,
  validInput,
} from "../src/shared/validation";

describe("shared Python / TypeScript contract fixtures", () => {
  for (const sample of samples)
    it(sample.name, () => {
      const validator =
        domainValidators[sample.model as keyof typeof domainValidators];
      expect(validator(sample.data)).toBe(sample.valid);
    });
});
it("rejects arbitrary IPC methods, URLs, extra arguments and malformed cursors", () => {
  expect(validInput("fetch", { url: "https://example.com" })).toBe(false);
  expect(validInput("__proto__", {})).toBe(false);
  expect(validInput("toString", {})).toBe(false);
  expect(validInput("constructor", {})).toBe(false);
  expect(validInput("state", { token: "injected" })).toBe(false);
  expect(validInput("events", { project_id: "bad", after: -1 })).toBe(false);
  expect(
    validInput("projects", { archived: false, tenant_id: "injected" }),
  ).toBe(false);
  expect(validInput("state", undefined)).toBe(true);
  for (const url of [
    "https://127.0.0.1:8000",
    "http://example.com",
    "http://127.0.0.1:8000/path",
    "http://user:pass@127.0.0.1:8000",
  ]) {
    expect(() => localServiceUrl(url)).toThrow();
  }
  expect(localServiceUrl("http://127.0.0.1:8000/")).toBe(
    "http://127.0.0.1:8000",
  );
});
