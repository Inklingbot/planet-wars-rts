## Scope and change boundaries

- For explanation, diagnosis, setup, or launch requests, do not modify source
  code unless the user explicitly authorizes a change.
- Treat existing uncommitted changes as user-owned.
- If source code blocks the requested task, explain the blocker and ask for
  approval before changing it.
- Cleanup and readability changes are allowed only after:
  1. Explaining why the existing code is egregiously unclear or problematic.
  2. Identifying the files or code regions involved.
  3. Receiving explicit user approval.
- Keep approved cleanup separate from the required functional change when
  practical.

## Repository command autonomy

- Run ordinary, non-destructive repository-local commands without asking for
  confirmation when they are needed for the current task.
- This includes reading and searching files, inspecting Git status or diffs,
  and running existing builds or tests.
- Do not ask the user to run a command that the agent can safely run itself.
- Request approval for destructive commands, dependency installation,
  network access, credentials, commits, pushes, or actions outside the
  repository.
- If the execution environment itself requires approval, explain the reason
  concisely and request only the narrowest permission needed.

## Reporting changes

- After making changes, provide a high-level explanation of each change.
- Provide detailed diffs or audits only when the user requests them.
