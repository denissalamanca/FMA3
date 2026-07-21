# Worktree playbook — running parallel Claude Code sessions on one repo

**Problem this solves:** two (or more) Claude Code sessions sharing ONE working
directory step on each other — the checkout can only be on one branch at a time,
so a `git checkout` in one session yanks the tree out from under the other. We hit
this live: while the EA session believed it was on `main`, the backtest session had
the shared tree on its `chore/recon-17…` branch. No amount of "one git op at a time"
discipline fully fixes it.

**Fix:** one **git worktree** per session — separate directories, separate checkouts,
one shared `.git`. Lightweight (the `.git` is shared; a worktree adds only a checkout,
not a re-clone).

---

## Precondition — start from a clean `main`

Do this only when the primary session's tree is on `main` and clean (nothing
mid-flight):

```bash
git checkout main && git pull      # on main, up to date
git status                         # must be clean
```

## Setup — three commands per new session

Example: a new FMA5 backtest effort (`fma5-backtests`).

**1. Create the worktree** — a sibling directory on its own new branch:

```bash
git worktree add /Users/dsalamanca/vs_env/FMA3-fma5-backtests -b fma5-backtests
```

To continue an *existing* branch instead, drop `-b` and name it:
`git worktree add <path> existing-branch`.

**2. Launch Claude Code in that directory** — a new terminal:

```bash
cd /Users/dsalamanca/vs_env/FMA3-fma5-backtests
claude
```

That session's working dir is the worktree — isolated checkout, its own branch.

**3. Hand it a self-contained kickoff.** This matters MORE with worktrees: Claude's
project memory is keyed to the **directory path**, so a worktree at a new path gets a
**separate** memory store — it will NOT auto-load the FMA3 `MEMORY.md`. Either bake the
needed context into the kickoff, or begin the kickoff with:

> First read `/Users/dsalamanca/.claude/projects/-Users-dsalamanca-vs-env-FableMultiAssets3/memory/MEMORY.md`
> for shared project context.

## Working + merging

- Each session commits to **its own branch**, pushes, and PRs on GitHub — as now, but
  with zero tree collisions.
- To pull main into a worktree: `git pull origin main` (or `git merge main`) *inside
  that worktree*.

## Cleanup when the line of work ends

```bash
git worktree remove /Users/dsalamanca/vs_env/FMA3-fma5-backtests
git branch -d fma5-backtests        # if fully merged
```

## The three rules that keep it clean

1. **One branch per worktree** — git enforces this; a branch checked out in one
   worktree cannot be checked out in another. Each worktree on a distinct branch.
2. **`main` stays in the primary worktree** (the original repo dir). Don't check out
   `main` in a secondary one — it's needed in the primary for pulls/merges. Feature
   branches go in the secondaries.
3. **Worktree dirs are *siblings* of the repo** (`FMA3-<purpose>`), never nested
   *inside* the repo folder.

---

*Alternatives, for the record:* separate full clones (fully isolated, but re-clones the
multi-GB `.git` each — heavier, no shared refs); or the single-tree "one git op at a
time" discipline (fragile — this playbook exists because that failed in practice).
Worktrees are the balance and the standard practice for multi-agent work on one repo.
