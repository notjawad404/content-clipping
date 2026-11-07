# Paste a Link, Get Clips Posted to Instagram — Design Spec

**Date:** 2026-11-08
**Status:** Approved in brainstorming; pending written-spec review
**Builds on:** `2026-11-07-clipper-design.md` (clip pipeline) and `2026-11-07-instagram-posting-design.md` (queue + posting workflow, live since 2026-11-07)

## 1. Goal

In a new Claude Code session in this repo, the user pastes a YouTube link. Claude makes up to 5 clips, checks them, and posts all of them to Instagram as Reels with no further input. The user can change this in plain words: a count ("only 3", "10 clips"), or "schedule them" / "spread them through the day", or "review first".

### Success criteria
- A bare link produces up to 5 clips and posts every clip that passes the quality bar and the visual check, then reports every Reel link.
- A count in the prompt overrides the default of 5.
- "Schedule" wording queues the clips and leaves posting to the cron; nothing is posted immediately.
- The campaign is chosen from the video, only on a clear match, and the choice is reported.
- A failure at any step stops posting, is reported with the failing run's link, and loses nothing already queued.

### Decisions (from brainstorming)
| Question | Decision |
|---|---|
| Default count | 5 (`max_clips: 5` in `config/style.yaml`; user count overrides) |
| Fewer than 5 clear the bar (score ≥ 7.0) | Post only the good ones and say how many and why |
| Default mode | Post now, back to back |
| "Schedule" mode | Queue only; the existing cron posts (09:00, 13:00, 19:00 UTC, one clip per run, so 3 a day) |
| Campaign when none is named | Chosen from the video; only on a clear match, otherwise none; always reported; an explicitly named campaign always wins |
| Confirmation before posting | None by default (fully automatic); "review first" keeps the existing stop before rendering |

### Out of scope
New cron times (the user can ask separately), per-clip captions review, TikTok/YouTube/X posting, retrying failed posts automatically, changing the posting workflow or the queue format.

## 2. `clipper post-now`

New module `clipper/publish/post_now.py` and subcommand `uv run clipper post-now`. It drains the queue by running the live workflow once per pending entry. It reuses the queue and config modules and adds no new dependency.

Algorithm (all `gh`/`git` calls go through an injectable `run`, as in `clips_repo.py`):
1. Refuse unless the current branch equals `queue_branch` (`master`), with the same one-line message as the `queue` command. Run `git pull --rebase --autostash` first so the local queue matches the remote.
2. `pending = queue.load_all(root, "pending")`. If empty, print "nothing to post" and exit 0. The loop is bounded by the number of entries pending at the start.
3. For the oldest pending entry (`queued_at`, then id; the same order `post_next` uses): record the ids of existing `workflow_dispatch` runs of `post-next.yml`, run `gh workflow run post-next.yml -f dry_run=false`, then poll `gh run list` (every 5 s, up to 90 s) for a new run id.
4. `gh run watch <id> --exit-status`. A non-zero exit means failure: print the run URL and stop with exit 1. No automatic retry; running `post-now` again continues from the queue.
5. After a successful run, `git pull --rebase --autostash`. The run must have moved the targeted entry to `queue/posted/<id>.json` (the permalink is printed when present; a post without a returned link is still a post and is reported with its media id). If it was not moved (for example the daily quota was reached, or the run found nothing to do), print which entry is still pending and why the run was green, and stop with exit 1 so the caller never reports a post that did not happen.
6. Print `posted <id>: <permalink>` and repeat from step 3 for the next entry.
7. At the end print `done: <n> posted`, where n is the number of entries that left `pending/` during the run, and exit 0.

A scheduled cron run that happens during `post-now` is safe: the workflow's concurrency group serializes runs, and step 5 checks the targeted entry, not the run. If the cron run posted the targeted entry first, the check still passes and the next loop iteration continues with the next entry.

Errors are typed (`PostNowError`, a `PublishError`); messages never contain tokens (the command never reads them). If `gh` is missing or not logged in, the command says so in one line before doing anything.

Other entries already pending from earlier runs are drained too, in order. The skill tells the user when that happens.

## 3. Skill changes (`.claude/skills/clipper/SKILL.md`)

- **Preflight** adds: `gh auth status` succeeds, and the current branch is `master` (switch with `git checkout master`; if that fails because of tracked local changes, stop and tell the user). Both checks run before any download so a problem shows up in the first minute, not after the render.
- **Step 1 (Read the request)** adds: the defaults above, how count, "schedule" and "review first" wording changes them, and the campaign-from-video rule: read `config/campaigns/*.yaml` (not `example.yaml`), compare each file's creator tag, name, required text and comments with the video's channel, title and description from `meta.json`, pick a campaign only on a clear match, otherwise none.
- **Step 6 (QA)**: a clip that still fails the visual check after one fix attempt is not queued; it is reported.
- **New step 7a (Queue and post)** before Finish: run `uv run clipper queue <video_id> --only <passing ids>`. In post-now mode run `uv run clipper post-now` with `run_in_background: true` (each post takes about two minutes) and wait; in schedule mode stop after `queue` and say when the cron will post them.
- **Step 7 (Finish)** final message lists: every Reel link, the chosen campaign (or "none"), any skipped or failed clips and why, any older pending entries that were also posted. Content Rewards reminder is kept: submit the post links within 30 minutes and do not edit the posts after submitting.

`config/style.yaml`: `max_clips: 5`. The README's description of the defaults is updated to match.

## 4. Testing

Unit tests with a fake `run` and a temp queue directory, no network: refuses off `master`; empty queue; happy path of three entries (posts in order, prints permalinks, summary count); stops at the first failed run and does not trigger the next; a green run that left the entry pending stops with exit 1; the new run id is found among pre-existing runs; the new-run poll times out cleanly; a cron-posted entry still satisfies the check; `gh` missing; CLI wiring and exit codes. Config test that `max_clips` is 5. The skill file is not unit-tested; a manual end-to-end run with a real link is the acceptance test (the first full run uses the user's chosen episode and is confirmed with them before it starts).

## 5. Risks

- **Fully automatic public posting.** Anything that slips past the visual check goes live. "Review first" is the opt-out.
- **Burst posting.** Five Reels about two minutes apart looks less natural than a drip and Instagram may treat it less favorably. This is the requested default; "schedule them" avoids it.
- **Wrong campaign.** Matching a campaign from the video is a judgment call and a wrong match puts the wrong required text on a public post. It is reported every time; naming the campaign removes the guess.
- **Schedule cadence.** The 3-a-day cron means 5 scheduled clips take two days.
- **Instagram limits.** The workflow already reads the live publishing quota and waits when it is reached; `post-now` reports that case as a stop, not a success.
