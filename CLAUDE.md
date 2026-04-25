# Repo rules for Claude

## Merging PRs — preserve authorship

When merging any PR, always use `gh pr merge <num> --squash --delete-branch` (or `--merge`/`--rebase` if a non-squash strategy is appropriate). GitHub sets the commit author to the PR author by default for these strategies, which preserves contribution credit and the "merged" badge on their profile.

**Never** do any of the following — they strip the original author off the commit and/or break the link from the PR to the merge:

- Closing the PR and re-implementing the change yourself.
- Checking out the branch locally, merging into main, and pushing — unless the final commit's `author` is explicitly the PR author.
- Cherry-picking commits and then closing the PR; the PR will show as "closed" not "merged" so the author loses profile credit.

After every merge, verify with:

```
gh pr view <num> --json state,mergedBy,author,mergeCommit
git log -1 --format="%h author=%an <%ae>%n%s"
```

The `author` of the squash commit must equal the PR author's GitHub identity, not yours.

If a PR branch is BEHIND main and merge is blocked, update it via:

```
gh api -X PUT "repos/<owner>/<repo>/pulls/<num>/update-branch"
```

This is allowed when `maintainerCanModify` is true on the PR (default for fork PRs unless the contributor opted out). Then wait for CI and merge as above.
