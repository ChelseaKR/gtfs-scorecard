# ADR 0038: use scoped system trust for feed TLS

**Status:** Accepted (2026-07-13)

## Context

The pipeline downloads feeds from public bodies in many jurisdictions. A
single bundled CA snapshot does not always match the roots available to the
host operating system or roots installed by an operator. This became visible
with Uruguay's official open-data catalog. Its server presented a Let's
Encrypt Root YR chain without the cross-certificate needed to reach ISRG Root
X1. The chain worked through the macOS trust service but failed with a current
Certifi bundle and on a default Linux OpenSSL client.

Let's Encrypt documents that Root YR is not yet in major root-program trust
stores. Its documented default YR1 chain continues through the Root YR
certificate cross-signed by ISRG Root X1. Chains ending directly at Root YR
are not expected to work broadly.

Sources:

- [Let's Encrypt chains of trust](https://letsencrypt.org/certificates/)
- [official Root YR cross-certificate signed by ISRG Root X1](https://letsencrypt.org/certs/gen-y/root-yr-by-x1.pem)
- [truststore documentation](https://truststore.readthedocs.io/en/stable/)

## Decision

`safe_get` creates a Requests session with a scoped `truststore.SSLContext` for
HTTPS. It does not inject a context into Python's global `ssl` module. Plain
HTTP keeps Requests' normal adapter.

The package also carries the official Root YR certificate cross-signed by
ISRG Root X1 as a temporary chain bridge. Before loading it, the pipeline
checks its DER SHA-256 fingerprint:

`07:26:39:D0:B1:40:D5:BF:FA:E1:6A:D9:C3:F6:CC:60:86:04:06:21:F5:1E:E6:1A:6D:46:A8:91:5C:07:CF:76`

OpenSSL partial-chain verification is explicitly disabled. The bridge is
therefore usable as an intermediate, but it cannot terminate trust. A client
must still reach an operating-system trust anchor such as ISRG Root X1.
Hostname validation and `CERT_REQUIRED` remain enabled. The pipeline never
uses a server-supplied root, disables verification, or pins a server IP.

The same context is used for HTTPS destinations reached through a proxy. The
session is closed after each guarded fetch.

## Consequences

- Feed hosts benefit from normal operating-system CA updates and locally
  administered trust policy.
- The affected official Uruguay feed works on Linux while preserving a chain
  to ISRG Root X1.
- A changed or corrupt packaged bridge stops the fetch before any connection.
- The runtime adds the small `truststore` dependency and one reviewed
  certificate resource.
- Remove the bridge after affected servers consistently present the default
  chain or Root YR is broadly available in root-program stores. Any bridge
  replacement requires a new official-source and fingerprint review.
