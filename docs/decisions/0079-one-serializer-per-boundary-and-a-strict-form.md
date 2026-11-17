# ADR 0079: One serializer per boundary, and a strict self-serve form

**Status:** Proposed (2026-11-17), for the maintainer's review. It becomes
Accepted when this change merges. 0078 is taken by `seo/agency-title-test`.

## Context

Text from outside the project crosses into something that interprets it in four
places:

- a registry name, note or URL is written as JSON inside a `<script>` element
  (JSON-LD on every page, and the values a few inline scripts read);
- a catalog value or a self-serve submission is written as YAML into a
  registry block that a pull request proposes;
- the gtfs-validator jar is downloaded and run with `java -jar`, in the daily
  job and in the workflow of everyone who uses the Action;
- a public, anonymous form post becomes a pull request opened with the
  maintainer's token.

Each had a local rule written for the values seen so far: `json.dumps` for the
script elements, a quoting heuristic for YAML, a version in the download URL for
the jar, and the registry loader's rules plus a gateway throttle for the form. A
review on 2026-11-17 found each rule narrower than the format or the trust it
stood in front of. This record replaces the four local rules with one stated
rule per boundary.

## Decision

1. **JSON in a script element is written by `site_shell.json_for_script`.** It
   is `json.dumps` with `<`, `>`, `&`, U+2028 and U+2029 written as `\u`
   escapes. Any JSON or JavaScript parser reads those back as the same
   characters, and the HTML parser never sees them. The page shell's JSON-LD,
   both offer regions, the compare page, the agency map, the map page's country
   labels and the route map's color expressions all use it. A test walks every
   f-string in the package and fails on `json.dumps` inside a script element.
   Inline attributes already go through `esc`, which escapes quotes.

2. **Every value in a rendered registry block is a PyYAML scalar, and the block
   is read back before it is returned.** `mobilitydb.render_yaml` keeps its
   hand-written layout so the output matches the registry's style. PyYAML's
   emitter decides whether a value can be plain. A value holding any line break
   YAML recognizes, a control character, or text that reads back as another
   type (`NO`, `123`, `null`) is written double-quoted on one line. The finished
   text is then parsed and compared with the entries it was written from, and a
   difference raises `RegistryRenderError`. Two inputs in front of the writer
   are narrowed as well: a catalog cell is read as one line, and the registry
   loader refuses a name holding a control character, a line separator, `<` or
   `>`, and a URL holding a control character or a space.

3. **The validator jar runs only if its SHA-256 matches a pinned digest.**
   `validate.VALIDATOR_JAR_SHA256` holds one digest per version beside
   `VALIDATOR_VERSION`. `ensure_validator` checks a fresh download and a cached
   copy alike. On a mismatch, or for a version with no pinned digest, it raises
   `ValidatorIntegrityError`: nothing is written to the cache and `java` is not
   started. It does not download again and try a second time. The canary, which
   exists to try an unpinned release, takes that release's digest as
   `--candidate-sha256`; a supplied digest can add a version and cannot replace
   a pinned one. The two container images already checked the same digest at
   build time, and `tests/test_validator_pin.py` holds all three to one version
   and one digest. Moving the pin is three steps, written on the constant and
   in `docs/rubric.md` under "Governed upgrades".

4. **The self-serve endpoint checks in a fixed order and uses its token last.**
   - The request body is at most 8 KB.
   - Every field is one the form has, is text, is within a per-field length
     limit, and holds only the characters that field takes
     (`submissions.validate_form`). Names and notes take letters, digits,
     spaces and ordinary punctuation in any script; control characters, line
     separators, format characters, symbols, and the punctuation Markdown and
     mentions use are refused. Feed URLs must be `http` or `https` on a public
     host name, with no credentials, IP literals or private names.
   - A per-client limit of 3 and a global limit of 20 submissions per UTC day,
     each one conditional write in the shared rate-limit table. A client is
     keyed by a hash of its address and the day, and the row expires within two
     days. The client limit is taken first, so one client at its own limit does
     not use up the global one.
   - If the limits cannot be checked, the endpoint says online submission is
     paused and points to the manual walkthrough. It does not open a pull
     request it cannot count.
   - Submitted values appear in the pull request body only inside code spans.
     The commit message names the derived id. The branch name is `submit-` plus
     that id, which is checked against the id shape. Request paths are built
     from configuration alone.
   - The API Gateway stage throttles to one request per second.

   A test holds every workflow and the Action to passing branch names, titles,
   bodies and commit messages through `env:`, which is what they do today.

## Considered and not done here

- **A challenge widget on the form.** It would add a third-party script to a
  page that has none. The daily limits bound the same thing. Worth revisiting
  if real submissions ever reach the global limit.
- **Holding submissions privately and opening pull requests in a batch.** That
  changes what the form promises, a pull request link in the reply, and is a
  product decision.
- **Moving the GitHub token out of the function's environment into a secrets
  store.** A separate change: it needs a new token and a rotation by the
  maintainer. Listed in `docs/follow-ups.md`.
- **`yaml.dump` for the whole block.** It would rewrite the registry's quoting
  and key style in every proposed block.
- **A site-wide Content-Security-Policy.** GitHub Pages cannot send the header,
  and a meta policy needs every inline script hashed. Out of scope here.

## Consequences

- Rendered pages are unchanged except that `&`, `<` and `>` inside JSON-LD now
  appear as `\u0026`, `\u003c` and `\u003e`. Search engines read the same JSON.
- A registry entry whose name holds `<`, `>` or a control character now fails
  to load. None of the 2,695 entries read on 2026-11-17 does.
- The form refuses some entries a maintainer could add by hand: a feed served
  from an IP address, a name with unusual punctuation. Its message points to
  `docs/add-your-agency.md`.
- Each scoring process hashes the 40 MB jar once before its first run.
- `scorecard canary` and `validator-canary.yml` need the candidate's digest.
- People using the Action get the jar check from the next tagged release.
- The endpoint changes take effect when `infra/submit` is rebuilt and applied
  (`docs/deploy.md`, section 3). The apply adds one IAM statement and three
  environment variables to the function and changes the stage throttle.
