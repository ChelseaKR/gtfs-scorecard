// Contract tests: the generated TypeScript client against recorded responses of the read API.
//
// Nothing here touches a network. A `fetch` that serves recorded files stands in
// for the host, and the typed client reads what it is given. The recordings are
// pipeline/tests/fixtures/golden_site (what the renderer writes for three
// agencies) plus real files copied out of data/artifacts/ under clients/fixtures/.
// clients/fixtures/manifest.json names the file behind every documented path.
//
// TypeScript types are erased, so "parses" here means two things. At runtime the
// typed client must fetch every documented path and hand back exactly the JSON
// that was served. At compile time (`npm run typecheck`, which includes this
// file) the generated types must say what the schemas say about absence: an
// optional field is `T | undefined`, a nullable one is `T | null`, and neither
// is a number. The `@ts-expect-error` lines are that second half; tsc fails on
// one that no longer errors.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import {
  checkSchemaVersion,
  createScorecardClient,
  SUPPORTED_SCHEMA_MAJOR,
  UnsupportedSchemaVersionError,
  type components,
} from "./index.ts";

const CLIENTS = new URL("../../", import.meta.url);
const REPO = new URL("../", CLIENTS);
const BASE_URL = "https://scorecard.test";

type Manifest = {
  samples: Record<string, string>;
  responses: Record<string, string | null>;
  not_recorded: Record<string, string>;
};
type Spec = {
  info: Record<string, unknown>;
  paths: Record<string, { get: { responses: Record<string, unknown> } }>;
  components: { responses: Record<string, { content: Record<string, unknown> }> };
};

const readText = (url: URL): string => readFileSync(url, "utf8");
const manifest = JSON.parse(readText(new URL("fixtures/manifest.json", CLIENTS))) as Manifest;
const spec = JSON.parse(readText(new URL("openapi.bundled.json", CLIENTS))) as Spec;
const recorded = (path: string): string => {
  const file = manifest.responses[path];
  assert.ok(file, `${path} has no recording`);
  return readText(new URL(file, REPO));
};

/** The media type of a path's 200 response. */
function mediaType(path: string): string {
  let response = spec.paths[path]?.get.responses["200"] as Record<string, unknown>;
  const ref = response.$ref;
  if (typeof ref === "string") {
    response = spec.components.responses[ref.split("/").pop() ?? ""] as Record<string, unknown>;
  }
  return Object.keys(response.content as Record<string, unknown>)[0] ?? "";
}

/** How openapi-fetch must read a body that is not JSON: as text, or as raw bytes. */
function parseAsFor(type: string): "text" | "arrayBuffer" | undefined {
  if (type === "application/json") {
    return undefined;
  }
  return type.startsWith("text/") || type.includes("xml") || type.includes("yaml")
    ? "text"
    : "arrayBuffer";
}

const concrete = (path: string): string =>
  path.replace(/{(\w+)}/g, (_, name: string) => manifest.samples[name] ?? name);

type Served = { body: string | Uint8Array; type: string };

/** A `fetch` that serves `{url path: response}` and answers 404 to everything else. */
function serve(routes: Record<string, Served>): typeof globalThis.fetch {
  return async (input) => {
    const request = input instanceof Request ? input : new Request(input as string);
    const served = routes[new URL(request.url).pathname];
    if (!served) {
      return new Response("not found", { status: 404 });
    }
    return new Response(served.body as BodyInit, {
      status: 200,
      headers: { "content-type": served.type },
    });
  };
}

function serving(path: string, body: string, guard = true) {
  return createScorecardClient({
    baseUrl: BASE_URL,
    guard,
    fetch: serve({ [concrete(path)]: { body, type: mediaType(path) } }),
  });
}

// A path chosen at run time cannot satisfy the literal-path types, so this
// describes the one call shape the loop below uses.
type Result = { data?: unknown; error?: unknown; response: Response };
type Dynamic = (path: string, init: unknown) => Promise<Result>;

const LATEST = "/data/artifacts/{agency_id}/latest.json";
const artifactFile = (id: string): string =>
  readText(new URL(`clients/fixtures/artifacts/${id}`, REPO));

describe("every documented path", () => {
  it("has a generated type", () => {
    const generated = readText(new URL("typescript/src/generated/schema.ts", CLIENTS));
    for (const path of Object.keys(spec.paths)) {
      assert.ok(generated.includes(`"${path}": {`), `${path} is missing from generated/schema.ts`);
    }
    assert.ok(Object.keys(spec.paths).length >= 50);
  });

  const recordedPaths = Object.entries(manifest.responses).filter(([, file]) => file !== null);
  for (const [path] of recordedPaths) {
    it(`is fetched and read through the typed client: ${path}`, async () => {
      const body = recorded(path);
      const type = mediaType(path);
      const client = serving(path, body);
      const parseAs = parseAsFor(type);
      const call = client.GET as unknown as Dynamic;
      const { data, error, response } = await call(path, {
        params: { path: manifest.samples },
        ...(parseAs ? { parseAs } : {}),
      });

      assert.equal(error, undefined, `${path} returned an error body`);
      assert.equal(response.status, 200);
      if (type === "application/json") {
        assert.deepEqual(data, JSON.parse(body) as unknown);
      } else if (parseAs === "text") {
        assert.equal(data, body);
      } else {
        assert.ok(data instanceof ArrayBuffer);
      }
    });
  }

  it("names a reason for each path it did not record", () => {
    const unrecorded = Object.entries(manifest.responses)
      .filter(([, file]) => file === null)
      .map(([path]) => path);
    assert.deepEqual(unrecorded.sort(), Object.keys(manifest.not_recorded).sort());
  });

  it("serves the documented 404 for a path with no recording", async () => {
    const client = createScorecardClient({ baseUrl: BASE_URL, fetch: serve({}) });
    const { data, response } = await client.GET("/api/v1/ridership-impact.json");
    assert.equal(response.status, 404);
    assert.equal(data, undefined);
    assert.ok("404" in (spec.paths["/api/v1/ridership-impact.json"]?.get.responses ?? {}));
  });

  it("reads JSON null from run-status.json as null, not as an object", async () => {
    const client = serving("/api/v1/run-status.json", recorded("/api/v1/run-status.json"));
    const { response, data } = await client.GET("/api/v1/run-status.json", { parseAs: "text" });
    assert.equal(response.status, 200);
    assert.equal(JSON.parse(data as string), null);
  });
});

describe("a value that was not measured is never a number", () => {
  type Artifact = components["schemas"]["Artifact"];

  it("leaves an unmeasured category without a score", async () => {
    const body = artifactFile("tper-marconi-express-2026-08-07.json");
    const client = serving(LATEST, body);
    const { data } = await client.GET(LATEST, { params: { path: { agency_id: "unitrans" } } });
    assert.ok(data, "the artifact did not parse");

    const realtime = data.categories.realtime;
    assert.equal(realtime.status, "not_yet_measured");
    assert.equal(realtime.score, undefined);
    assert.notEqual(realtime.score, 0);
    assert.equal("score" in realtime, false);
    // The measured categories keep their numbers.
    assert.equal(typeof data.categories.correctness.score, "number");

    // The types say the same thing, and tsc enforces it.
    const score: number | undefined = realtime.score;
    assert.equal(score, undefined);
    // @ts-expect-error a category's score may be absent, so it is not a `number`
    const asNumber: number = realtime.score;
    assert.equal(asNumber, undefined);
  });

  it("keeps a measured zero and a null distinct in the catalog", async () => {
    const path = "/catalog.json";
    const body = readText(new URL("clients/fixtures/documents/catalog-trimmed.json", REPO));
    const { data } = await serving(path, body).GET(path);
    assert.ok(data);
    const rows = new Map(data.agencies.map((row) => [row.id, row]));

    // Anchorage's one realtime feed was unhealthy in every sample: a measurement of zero.
    assert.strictEqual(rows.get("anchorage-people-mover")?.realtime, 0);
    // Barrie and London Transit publish no realtime feed the scorecard measured: null, not zero.
    for (const id of ["barrie-transit", "london-transit-commission", "10-15-transit"]) {
      assert.strictEqual(rows.get(id)?.realtime, null, id);
      assert.strictEqual(rows.get(id)?.national_percentile, null, id);
    }

    type Row = components["schemas"]["CatalogAgency"];
    const nullable: Row["realtime"] = null;
    assert.equal(nullable, null);
    // @ts-expect-error a nullable field is not a plain number
    const plain: number = rows.get("barrie-transit")?.realtime;
    assert.equal(plain, null);
  });

  it("types the artifact's category status as the two values the schema allows", () => {
    type Status = Artifact["categories"]["realtime"]["status"];
    const measured: Status = "measured";
    const unmeasured: Status = "not_yet_measured";
    // @ts-expect-error only "measured" and "not_yet_measured" are allowed
    const other: Status = "zero";
    assert.deepEqual([measured, unmeasured, other], ["measured", "not_yet_measured", "zero"]);
  });

  it("reads every recorded artifact's realtime score as a number only when it was measured", () => {
    const files = [
      "tper-marconi-express-2026-08-07.json",
      "washington-park-shuttle-2026-08-07.json",
      "fort-matanzas-ferry-2026-08-07.json",
      "brightline-trains-llc-2026-08-07.json",
      "selah-transit-2026-08-07.json",
      "hut-airport-shuttle-2026-07-16.json",
    ];
    let unmeasured = 0;
    for (const file of files) {
      const artifact = JSON.parse(artifactFile(file)) as Artifact;
      const realtime = artifact.categories.realtime;
      if (realtime.status === "not_yet_measured") {
        unmeasured += 1;
        assert.equal(realtime.score, undefined, file);
      } else {
        assert.equal(typeof realtime.score, "number", file);
      }
    }
    assert.ok(unmeasured >= 3, "the recordings no longer include unmeasured realtime categories");
  });
});

describe("the schema_version guard", () => {
  const unitrans = (): Record<string, unknown> =>
    JSON.parse(recorded(LATEST)) as Record<string, unknown>;
  const get = (client: ReturnType<typeof createScorecardClient>) =>
    client.GET(LATEST, { params: { path: { agency_id: "unitrans" } } });

  it("names the major the description names", () => {
    assert.equal(spec.info["x-artifact-schema-version-major"], SUPPORTED_SCHEMA_MAJOR);
  });

  it("fails on a major version bump", async () => {
    const bumped = JSON.stringify({ ...unitrans(), schema_version: "2.0" });
    await assert.rejects(get(serving(LATEST, bumped)), (error: unknown) => {
      assert.ok(error instanceof UnsupportedSchemaVersionError);
      assert.equal(error.found, "2.0");
      assert.match(error.message, /Upgrade the client/);
      return true;
    });
  });

  it("tolerates a minor version bump and a field it has never heard of", async () => {
    const document = { ...unitrans(), schema_version: "1.99", a_future_field: { added: true } };
    const { data } = await get(serving(LATEST, JSON.stringify(document)));
    assert.equal(data?.schema_version, "1.99");
    assert.deepEqual((data as Record<string, unknown>).a_future_field, { added: true });
  });

  it("can be turned off", async () => {
    const bumped = JSON.stringify({ ...unitrans(), schema_version: "2.0" });
    const { data } = await get(serving(LATEST, bumped, false));
    assert.equal(data?.schema_version, "2.0");
  });

  it("also guards a document versioned separately, such as dataset.json", async () => {
    const path = "/dataset.json";
    const bumped = JSON.stringify({ ...(JSON.parse(recorded(path)) as object), schema_version: "2.0" });
    await assert.rejects(serving(path, bumped).GET(path), UnsupportedSchemaVersionError);
  });

  it("does not check a body that is not a versioned document", async () => {
    for (const path of ["/api/v1/run-status.json", "/catalog.csv", "/changes/feed.xml"] as const) {
      const { response } = await serving(path, recorded(path)).GET(path, { parseAs: "text" });
      assert.equal(response.status, 200, path);
    }
  });

  const refused: [unknown, RegExp][] = [
    [{ schema_version: "2.0" }, /major version 2/],
    [{ schema_version: 2 }, /major version 2/],
    [{ schema_version: null }, /not a version string/],
    [{ schema_version: true }, /not a version string/],
    [{ schema_version: ["1"] }, /not a version string/],
    [{}, /no schema_version/],
    ["3.1", /major version 3/],
  ];
  for (const [document, message] of refused) {
    it(`refuses ${JSON.stringify(document)}`, () => {
      assert.throws(() => checkSchemaVersion(document), message);
    });
  }

  it("accepts a same-major document, a bare version, and a missing version when not required", () => {
    checkSchemaVersion({ schema_version: "1.19" });
    checkSchemaVersion("1.19");
    checkSchemaVersion(1);
    checkSchemaVersion({}, { require: false });
    assert.throws(() => checkSchemaVersion("1.19", { supportedMajor: "2" }), /major version 1/);
  });
});
