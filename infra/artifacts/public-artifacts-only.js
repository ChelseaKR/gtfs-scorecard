function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // This distribution fronts a mixed-use bucket. Only the published artifact
  // tree and the public liveness document belong on the CDN. In particular,
  // feeds/ contains content-addressed source archives and cache/ contains
  // internal validator results. data/artifacts/run/ is an internal input whose
  // registry-bounded projection is published by Pages as api/v1/run-status.json.
  var isPublishedArtifact =
    uri.indexOf("/data/artifacts/") === 0 &&
    uri.indexOf("/data/artifacts/run/") !== 0;
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
