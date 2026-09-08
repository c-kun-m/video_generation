import type { Fault, Reply } from "../../../shared/bridge";

export class BridgeError extends Error {
  constructor(public detail: Fault) {
    super(detail.message);
  }
}
export async function unwrap<T>(result: Promise<Reply<T>>): Promise<T> {
  const reply = await result;
  if (!reply.ok) throw new BridgeError(reply.error);
  return reply.data;
}
