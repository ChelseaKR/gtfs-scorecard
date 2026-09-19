// Typed client for the GTFS Scorecard static read API.
//
// `./generated/schema.ts` is written by `make clients` from the OpenAPI
// description and is not edited by hand. This file and `./guard.ts` are.

import createClient, { type Client, type Middleware } from "openapi-fetch";

import type { paths } from "./generated/schema.ts";
import { checkSchemaVersion } from "./guard.ts";

export type { components, operations, paths } from "./generated/schema.ts";
export {
  checkSchemaVersion,
  SUPPORTED_SCHEMA_MAJOR,
  UnsupportedSchemaVersionError,
  type CheckOptions,
} from "./guard.ts";

/** The public instance. A fork's own host works anywhere a base URL is taken. */
export const DEFAULT_BASE_URL = "https://gtfsscorecard.org";

export interface ScorecardClientOptions {
  /** Where the files are served. Defaults to https://gtfsscorecard.org. */
  baseUrl?: string;
  /** Check every JSON response's `schema_version`. Default true. */
  guard?: boolean;
  /** A `fetch` to use in place of the global one. Tests use it to serve recordings. */
  fetch?: typeof globalThis.fetch;
}

/** A response middleware that refuses a JSON object whose `schema_version` major is unsupported. */
export const schemaVersionGuard: Middleware = {
  async onResponse({ response }) {
    const type = (response.headers.get("content-type") ?? "").toLowerCase();
    if (!response.ok || !type.includes("json")) {
      return undefined;
    }
    let body: unknown;
    try {
      body = await response.clone().json();
    } catch {
      // Not this guard's job: a malformed body is the caller's parse error.
      return undefined;
    }
    // `run-status.json` is JSON null until a run publishes one. That is not a
    // document that lost its version.
    if (typeof body === "object" && body !== null && !Array.isArray(body)) {
      checkSchemaVersion(body, { require: false });
    }
    return undefined;
  },
};

/**
 * A typed client over every path in the description.
 *
 * The API is static files: there is no key and no session. Absence stays
 * absence in the types: an optional field is `T | undefined` and a nullable one
 * is `T | null`, so an unmeasured value is never typed as a number.
 */
export function createScorecardClient(options: ScorecardClientOptions = {}): Client<paths> {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? DEFAULT_BASE_URL,
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  if (options.guard ?? true) {
    client.use(schemaVersionGuard);
  }
  return client;
}
