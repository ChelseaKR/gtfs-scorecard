# Container image for the instant-score Lambda (growth-plans 03-A4 / 06 Tier
# 1): an on-demand runner behind API Gateway that scores any GTFS URL a
# visitor pastes into web/try.html. Same JVM-plus-pipeline base as
# infra/compute's worker image, since this handler also shells out to the
# Java validator via scorecard_pipeline.cli.run_adhoc.
FROM public.ecr.aws/lambda/python:3.12

# Apply Amazon Linux security fixes from a reviewed, content-addressed
# repository snapshot, then add Java 17 for the validator jar. The immutable
# GUID avoids both the stale base-image snapshot and a mutable `latest` build.
ARG AL2023_REPO_GUID=734118c8c7ea0750e3f184363d93c6ad06b86a9eae3b1f1b6f3b98b21128bee2
RUN mkdir -p /tmp/al2023-pinned \
    && printf '%s\n' \
        '[amazonlinux]' \
        'name=Amazon Linux 2023 pinned security snapshot' \
        "baseurl=https://cdn.amazonlinux.com/al2023/core/guids/${AL2023_REPO_GUID}/\$basearch/" \
        'enabled=1' \
        'gpgcheck=1' \
        'gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-amazon-linux-2023' \
        > /tmp/al2023-pinned/amazonlinux.repo \
    && dnf upgrade -y --setopt=reposdir=/tmp/al2023-pinned \
    && dnf install -y --setopt=reposdir=/tmp/al2023-pinned java-17-amazon-corretto-headless \
    && dnf clean all \
    && rm -rf /tmp/al2023-pinned

# The pipeline package (this handler imports scorecard_pipeline.cli.run_adhoc).
COPY pipeline /opt/pipeline
# Hatch maps this immutable public schema into the installed wheel. Preserve
# the repository-relative source path while building the package in the image.
COPY web/schemas/sync-source-metadata-1.2.schema.json /opt/web/schemas/sync-source-metadata-1.2.schema.json
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
