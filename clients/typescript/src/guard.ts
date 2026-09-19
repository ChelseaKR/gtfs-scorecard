// The `schema_version` guard. Written by hand; `make clients` never touches it.
//
// docs/api.md asks consumers to tolerate added fields and to treat a change in
// the major version as a breaking change. This is that rule: a document whose
// major version is not the one this client was generated against is refused
// instead of being read through types that may no longer describe it. A test in
// the repository binds SUPPORTED_SCHEMA_MAJOR to `x-artifact-schema-version-major`
// in the OpenAPI description, so the two cannot drift apart.

/** The `schema_version` major this client's types were generated against. */
export const SUPPORTED_SCHEMA_MAJOR = "1";

/** A document carries a `schema_version` major this client was not generated for. */
export class UnsupportedSchemaVersionError extends Error {
  readonly found: unknown;

  constructor(message: string, found?: unknown) {
    super(message);
    this.name = "UnsupportedSchemaVersionError";
    this.found = found;
  }
}

function majorOf(version: unknown): string {
  if (typeof version === "string" || (typeof version === "number" && Number.isInteger(version))) {
    return String(version).split(".", 1)[0] ?? "";
  }
  throw new UnsupportedSchemaVersionError(
    `schema_version ${JSON.stringify(version)} is not a version string`,
    version,
  );
}

export interface CheckOptions {
  /** The major to accept. Defaults to the one this client was generated against. */
  supportedMajor?: string;
  /** Refuse a document with no `schema_version`. Default true. */
  require?: boolean;
}

/**
 * Throws UnsupportedSchemaVersionError unless the document's major version
 * matches. `document` is a parsed JSON object or a bare version string.
 */
export function checkSchemaVersion(document: unknown, options: CheckOptions = {}): void {
  const supported = options.supportedMajor ?? SUPPORTED_SCHEMA_MAJOR;
  const require = options.require ?? true;

  let version: unknown = document;
  if (typeof document === "object" && document !== null && !Array.isArray(document)) {
    if (!("schema_version" in document)) {
      if (require) {
        throw new UnsupportedSchemaVersionError("the document carries no schema_version");
      }
      return;
    }
    version = (document as Record<string, unknown>).schema_version;
  }

  const found = majorOf(version);
  if (found !== supported) {
    throw new UnsupportedSchemaVersionError(
      `schema_version ${JSON.stringify(version)} has major version ${found}; this client was ` +
        `generated against major version ${supported}. Upgrade the client.`,
      version,
    );
  }
}
