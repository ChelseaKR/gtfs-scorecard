# Deployment environments audit

A dated record of the repository's GitHub deployment environments and their
protection rules, per CI-CD-STANDARD §8a and audit finding CICD-22. Append a
new dated section at each review: quarterly, or whenever an environment is
added or a protection rule changes.

Read the live state with:

```sh
gh api repos/ChelseaKR/gtfs-scorecard/environments
```

## 2026-07-17

| Environment | Protection rules | Required reviewers |
|---|---|---|
| `github-pages` | branch policy (deploys from the default branch only) | none |

One environment exists. Its branch policy stops a pushed branch or tag from
deploying the site, and the `lighthouse` job inside `pages.yml` gates the
deploy on accessibility and performance budgets. No required-reviewer rule is
set, so no human approval stands between a merge to `main` and a Pages deploy.

Adding a reviewer requirement is a repository setting only the owner can
change: Settings → Environments → `github-pages` → Required reviewers. Until
then, this note records the gap rather than claiming the control exists. Note
the trade-off before enabling it: the hourly scheduled refresh deploys through
the same environment, and a required reviewer would hold every hourly deploy
for manual approval.
