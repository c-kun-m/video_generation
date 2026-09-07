import { afterEach, expect, it, vi } from "vitest";
import { Service } from "../src/main/service";
import type { Vault } from "../src/main/vault";
import type { Schema } from "../src/shared/bridge";

const identity: Schema["Identity"] = {
  actor_id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "22222222-2222-4222-8222-222222222222",
  session_id: "33333333-3333-4333-8333-333333333333",
  role: "owner",
  workspace_name: "fixture workspace",
  display_name: "fixture actor",
};
function vault() {
  return {
    data: {
      token: "expired-fixture-token",
      identity,
      pending: [
        {
          kind: "create",
          body: {
            command_id: "44444444-4444-4444-8444-444444444444",
            title: "preserved request",
          },
        },
      ],
    },
    save: vi.fn(),
  } as unknown as Vault;
}
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => vi.unstubAllGlobals());
it("renews an expired identity without losing the original pending command", async () => {
  const storage = vault();
  const original = JSON.stringify(storage.data.pending);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) =>
      request.url.endsWith("/me")
        ? response(
            { error: { code: "UNAUTHENTICATED", message: "expired" } },
            401,
          )
        : response({
            identity: {
              ...identity,
              session_id: "55555555-5555-4555-8555-555555555555",
            },
            access_token: "renewed-fixture-token",
            expires_at: "2099-01-01T00:00:00Z",
          }),
    ),
  );
  const service = new Service("http://127.0.0.1:8000", storage, "test");
  await service.dispatch("pair", {
    pairing_code: "fixture-code-only",
    device_name: "fixture",
  });
  expect(storage.data.token).toBe("renewed-fixture-token");
  expect(JSON.stringify(storage.data.pending)).toBe(original);
});
it("does not transfer unresolved writes to a different workspace identity", async () => {
  const storage = vault();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) =>
      request.url.endsWith("/me")
        ? response(
            { error: { code: "UNAUTHENTICATED", message: "expired" } },
            401,
          )
        : response({
            identity: {
              ...identity,
              tenant_id: "66666666-6666-4666-8666-666666666666",
            },
            access_token: "other-fixture-token",
            expires_at: "2099-01-01T00:00:00Z",
          }),
    ),
  );
  const service = new Service("http://127.0.0.1:8000", storage, "test");
  await expect(
    service.dispatch("pair", {
      pairing_code: "fixture-code-only",
      device_name: "fixture",
    }),
  ).rejects.toMatchObject({ fault: { code: "IDENTITY_MISMATCH" } });
  expect(storage.data.token).toBe("expired-fixture-token");
  expect(storage.data.pending).toHaveLength(1);
});
it("replays the original payload only after command lookup returns 404", async () => {
  const storage = vault();
  const body = storage.data.pending[0].body;
  const requests: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push({
        path: new URL(request.url).pathname,
        body: request.method === "GET" ? null : await request.json(),
      });
      return request.method === "GET"
        ? response({ error: { code: "NOT_FOUND", message: "missing" } }, 404)
        : response(
            {
              command_id: body.command_id,
              status: "APPLIED",
              project: null,
              error: null,
            },
            201,
          );
    }),
  );
  const service = new Service("http://127.0.0.1:8000", storage, "test");
  await service.dispatch("recover", { command_id: body.command_id });
  expect(requests).toEqual([
    { path: `/video/v1/commands/${body.command_id}`, body: null },
    { path: "/video/v1/projects", body },
  ]);
  expect(storage.data.pending).toHaveLength(0);
});
