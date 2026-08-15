function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // This distribution fronts a mixed-use bucket. Public access is a positive
  // filename contract, not a broad prefix: any new pipeline-state filename is
  // private until it is deliberately added here and to the origin policy.
  // Active registry membership is enforced by the serialized publisher: when
  // an id retires, its exact mutable names below are deleted while date-shaped
  // historical evidence remains available.
  var isRootArtifact = /^\/data\/artifacts\/(directory|index|scoring|sensitivity|canada-equity)\.json$/.test(uri);
  var isChangeArtifact = /^\/data\/artifacts\/changes\/(latest|[0-9]{4}-[0-9]{2}-[0-9]{2})\.json$/.test(uri);
  var isRollupArtifact = /^\/data\/artifacts\/rollups\/(index|[a-z0-9-]+)\.(json|csv)$/.test(uri);
  var isReservedNamespace = /^\/data\/artifacts\/(changes|rollups|run)\//.test(uri);
  var isAgencyArtifact = !isReservedNamespace && /^\/data\/artifacts\/[a-z0-9][a-z0-9-]*\/(latest\.json|[0-9]{4}-[0-9]{2}-[0-9]{2}\.json|badge\.(json|svg)|conformance\.json|mark\.svg|geometry\.geojson)$/.test(uri);
  var isPublishedArtifact =
    isRootArtifact || isChangeArtifact || isRollupArtifact || isAgencyArtifact;
  var isPublicLiveness = uri === "/data/liveness.json";

  if (isPublishedArtifact || isPublicLiveness) {
    return request;
  }

  return {
    statusCode: 404,
    statusDescription: "Not Found",
    headers: {
      "cache-control": { value: "no-store" },
      "content-type": { value: "text/plain; charset=utf-8" }
    }
  };
}
