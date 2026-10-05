import { afterEach, describe, expect, it, vi } from "vitest";
import { getAccessToken, refresh } from "./client.js";

const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("refresh", () => {
  it("retries once when another tab rotated the session a moment ago", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn()
      .mockResolvedValueOnce(reply(401, { error: { code: "refresh_raced", message: "raced" } }))
      .mockResolvedValueOnce(reply(200, { access_token: "new-token" }));
    vi.stubGlobal("fetch", fetch);

    const pending = refresh();
    await vi.runAllTimersAsync();
    await expect(pending).resolves.toMatchObject({ access_token: "new-token" });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe("new-token");
  });

  it("gives up straight away on a real failure", async () => {
    const fetch = vi.fn().mockResolvedValue(reply(401, { error: { code: "refresh_expired", message: "expired" } }));
    vi.stubGlobal("fetch", fetch);

    await expect(refresh()).rejects.toMatchObject({ code: "refresh_expired" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
