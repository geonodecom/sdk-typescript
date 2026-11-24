import { describe, expect, it } from "vitest";

import { Configuration } from "../src/index.js";

describe("Configuration", () => {
  // The default host comes from `servers` in openapi.json; a regeneration that loses it points the client at localhost.
  it("defaults to the production API", () => {
    expect(new Configuration().basePath).toBe("https://scraper.geonode.io");
  });
});
