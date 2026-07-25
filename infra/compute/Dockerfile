# Container image for the validator worker (Year 2, docs/roadmap.md).
# A JVM base so the MobilityData gtfs-validator runs in-process, with Python and
# the pipeline installed on top. Used as a Lambda container image or an ECS task.
FROM public.ecr.aws/lambda/python:3.12

# Apply Amazon Linux security fixes from a reviewed repository snapshot, then
# add Java 17 for the validator jar. AL2023 base images stay locked to their
# original repository snapshot unless --releasever is explicit.
RUN dnf upgrade -y --releasever=2023.12.20260720 \
    && dnf install -y --releasever=2023.12.20260720 java-17-amazon-corretto-headless \
    && dnf clean all

# The pipeline package (CLI entrypoint: `scorecard`).
COPY pipeline /opt/pipeline
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
