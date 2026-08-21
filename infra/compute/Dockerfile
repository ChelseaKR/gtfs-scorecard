# Container image for the validator worker (Year 2, docs/roadmap.md).
# A JVM base so the MobilityData gtfs-validator runs in-process, with Python and
# the pipeline installed on top. Deployed as a Lambda container image
# (`package_type = "Image"` in main.tf). An ECS task would have to override the
# entrypoint to run `scorecard` directly: the base image's default entrypoint
# needs the runtime emulator this Dockerfile removes below, and the ECS
# cluster/task wiring is not written (see main.tf).
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

# Drop the AWS Lambda Runtime Interface Emulator. It is a local-testing shim
# the base image ships at /usr/local/bin/aws-lambda-rie, and it is the only
# thing in this image built from Go, so its vendored Go standard library is a
# standing source of container CVEs (eight fixable HIGHs as of 2026-08-16,
# fixed in Go 1.26.6, which AWS has not yet rebuilt the emulator against).
# Nothing in this repository runs these images outside Lambda: infra/compute
# and infra/instant-score both deploy them as `package_type = "Image"`
# functions, so the managed runtime always sets AWS_LAMBDA_RUNTIME_API and
# /lambda-entrypoint.sh execs /var/runtime/bootstrap directly, never the
# emulator. The grep is the guard, not decoration: if a future base image
# stops gating the emulator on that variable, the entrypoint could need it on
# the managed path, and this build fails loudly instead of shipping an image
# whose entrypoint is missing. Consequence of the removal: `docker run` of
# this image on a workstation no longer emulates the Lambda API.
RUN grep -qF -- '-z "${AWS_LAMBDA_RUNTIME_API}"' /lambda-entrypoint.sh \
    && rm -f /usr/local/bin/aws-lambda-rie

# The pipeline package (CLI entrypoint: `scorecard`).
COPY pipeline /opt/pipeline
# Hatch maps this immutable public schema into the installed wheel. Preserve
# the repository-relative source path while building the package in the image.
COPY web/schemas/sync-source-metadata-1.2.schema.json /opt/web/schemas/sync-source-metadata-1.2.schema.json
RUN pip install --no-cache-dir /opt/pipeline boto3

# Cache the validator jar into the image so cold starts do not download it.
ENV SCORECARD_VALIDATOR_JAR=/opt/validator/gtfs-validator.jar
COPY data/cache/gtfs-validator-8.0.1-cli.jar ${SCORECARD_VALIDATOR_JAR}
# Verify the jar is the published MobilityData v8.0.1 CLI release; a poisoned
# build-context cache fails the build rather than shipping silently.
RUN echo "19293ddd9b6f954f216d4f12054bd8a3232921751c4484339e339764a91000e2  ${SCORECARD_VALIDATOR_JAR}" | sha256sum -c -

# The worker handler (SQS -> score one agency -> upload).
COPY infra/compute/worker.py ${LAMBDA_TASK_ROOT}/worker.py
# No USER directive: the AWS Lambda runtime executes handlers as its own
# non-root service user, and the official lambda/python base image relies on
# the runtime interface client owning the entrypoint.
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["worker.handler"]
