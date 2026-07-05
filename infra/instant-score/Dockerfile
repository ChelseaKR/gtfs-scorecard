# Container image for the instant-score Lambda (growth-plans 03-A4 / 06 Tier
# 1): an on-demand runner behind API Gateway that scores any GTFS URL a
# visitor pastes into web/try.html. Same JVM-plus-pipeline base as
# infra/compute's worker image, since this handler also shells out to the
# Java validator via scorecard_pipeline.cli.run_adhoc.
FROM public.ecr.aws/lambda/python:3.12

# Java 17 for the validator jar.
RUN dnf install -y java-17-amazon-corretto-headless && dnf clean all

# The pipeline package (this handler imports scorecard_pipeline.cli.run_adhoc).
COPY pipeline /opt/pipeline
RUN pip install --no-cache-dir /opt/pipeline boto3

# Bake the validator jar into the image so a cold start never depends on a
# network call to GitHub Releases. handler.py's _prepare_runtime copies this
# into the pipeline's own cache path (ensure_validator's lookup path) on first
# use; keep this destination in sync with its BAKED_VALIDATOR_JAR default.
COPY data/cache/gtfs-validator-8.0.1-cli.jar /opt/validator/gtfs-validator-cli.jar
# Verify the jar is the published MobilityData v8.0.1 CLI release; a poisoned
# build-context cache fails the build rather than shipping silently.
RUN echo "19293ddd9b6f954f216d4f12054bd8a3232921751c4484339e339764a91000e2  /opt/validator/gtfs-validator-cli.jar" | sha256sum -c -

COPY infra/instant-score/handler.py ${LAMBDA_TASK_ROOT}/handler.py
# No USER directive: the AWS Lambda runtime executes handlers as its own
# non-root service user, and the official lambda/python base image relies on
# the runtime interface client owning the entrypoint.
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["handler.handler"]
