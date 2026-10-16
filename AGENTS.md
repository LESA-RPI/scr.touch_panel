# Contributors and agents

- SCR is a small, trusted room project. Prefer short, practical changes and
  readable controls over new layers, release bureaucracy or speculative features.
  Keep everyday actions direct and detailed controls together in Room tools.
- Keep common panel and website behaviour consistent. Use the plain version from
  app/panel_version.py; put Git/build details only in About. Refresh the private
  screenshot gallery and interactive demo after verified deployments.
- Read README.md for room-user behaviour, WORKFLOWS.md for operation, and
  docs/interface.md for profiles, events and adapter contracts. Technical details
  remain available to human maintainers; do not create parallel documentation.
- Public PRs, commits and docs lead with what changes, why, and the effect on users.
  Put necessary technical evidence below or link to its owner. Distinguish planned
  work, implemented behaviour, tested scope and unresolved limits. Avoid private
  incident history, credentials, host configuration and participant information.
- General panel code belongs here. Project-X owns its optional recorder integration.
  Preserve the original application and shared room-service owners. Verify the
  deployed version and exact process before live actions; do not reuse old PIDs.
- One controller owns each hardware resource. Do not restart ROS/Status or install
  packages to make a query work. These launchers replace whole room sessions.
  Uncertain light results block writes and automatic retries; preserve receipts.
- Use an experiment branch and a draft PR. Do not merge to main without researcher
  approval. Never force-push or rewrite history. Keep commits cohesive.
- Run `python -m pytest tests` for code changes. For UI changes, check the target
  font/resolution, internal text fit, touch targets, wake behaviour and failure states.
  Docs-only changes need link and diff checks; they do not require a live reload.
- Keep one current private handoff with source/deployment, evidence, limits and the
  next check. README is the human entrypoint; code/contracts own technical detail.
