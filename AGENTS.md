# Contributors and agents

SCR is a small room project used mostly by students, researchers and visitors.
Keep it simple: small readable changes, no new layers or process unless they
remove more than they add.

- **Where things live:** README.md (room users), WORKFLOWS.md (setup and
  operation), docs/interface.md (contracts). Don't create parallel docs.
- **Consistency:** the panel and website share behaviour, wording and the version
  in app/panel_version.py. Headers say Beta; Git/build details appear only in About.
  Legacy (the original app) stays intact as the fallback.
- **Room safety:** one controller owns each piece of hardware. Never restart
  ROS/Status or install packages on room machines to make something work.
  Uncertain light results block changes and retries until checked. Before a live
  action, check the deployed version and the current process.
- **Ownership:** general panel code belongs here; Project-X owns its recorder
  integration.
- **Git:** work on a branch with a draft PR; the researcher approves merges to
  main. No force-push or history rewrites.
- **Checks:** `python -m pytest tests` (CI runs it on every push). For UI changes,
  look at the panel at 1280×800 and the website on phone and desktop, light and dark.
- **Writing:** PRs and commits lead with what changes for room users. Keep
  evidence short and below. No credentials, host details or participant information.
- Keep the short private handoff (.local/README.md) current after deployments.
