---
name: outbox-poller
description: Check for and process commissioned research tasks from Claude Code. Run the check_outbox.sh script to discover pending tasks in .claude/outbox/pending/, then pick up, execute, and deliver results back to the project.
---

# Outbox Task Poller

You are an external research agent. Claude Code places task files in `.claude/outbox/pending/` requesting research, data gathering, analysis, or validation. Your job is to find these tasks, do the work, and deliver structured results.

## When to Activate

Activate when the user says any of:
- "check outbox"
- "poll for tasks"
- "pick up work"
- "check for commissioned tasks"
- "any outbox tasks?"

## Protocol

### Step 1: Discover Pending Tasks

Run the discovery script from the workspace root:

```bash
bash .agent/skills/outbox-poller/scripts/check_outbox.sh .
```

If the script outputs `NO_TASKS`, report **"No pending outbox tasks."** and stop.

If the script outputs `PENDING_TASKS: N`, it will list each task with its ID, type, priority, created date, commissioner, and title. Present this summary to the user.

**If the script is not available**, fall back to listing the directory manually:

```bash
ls -la .claude/outbox/pending/OBX-*.md 2>/dev/null
```

If no files are found, report **"No pending outbox tasks."** and stop.

### Step 2: Select a Task

If multiple tasks exist, select by:
1. Priority: `urgent` first, then `normal`, then `low`
2. Date: oldest `created` timestamp first

Read the selected task file using `cat`:

```bash
cat .claude/outbox/pending/OBX-001_research_2026-02-11.md
```

Replace the filename with the actual task file from Step 1.

### Step 3: Claim the Task

Move the task file from `pending/` to `active/` and update its status:

```bash
mv .claude/outbox/pending/OBX-001_research_2026-02-11.md .claude/outbox/active/OBX-001_research_2026-02-11.md
```

Then edit the file to change `status: "pending"` to `status: "active"`.

Report: **"Claimed task {id}: {title}"**

### Step 4: Validate Constraints

Read the YAML frontmatter of the claimed task and verify:

| Field | Required Value | If Wrong |
|-------|---------------|----------|
| `constraints.read_only` | `true` | REJECT — move to `rejected/` |
| `constraints.no_code_changes` | `true` | REJECT — move to `rejected/` |
| `constraints.no_manifest_updates` | `true` | REJECT — move to `rejected/` |

To reject a task:

```bash
mv .claude/outbox/active/OBX-001_research_2026-02-11.md .claude/outbox/rejected/OBX-001_research_2026-02-11.md
```

Then edit the file: set `status: "rejected"` and append:
```yaml
rejected_at: "{ISO timestamp}"
rejection_reason: "Constraint validation failed: {field} was not true"
executor: "antigravity/gemini-3"
```

### Step 5: Check Expiry

Compare `created` + `constraints.timeout_hours` against the current time. Get the current time:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

If the task has expired, move to `rejected/` with `status: "expired"` and `rejection_reason: "Task expired after N hours without pickup"`. Stop processing.

### Step 6: Perform the Task

Read the task body carefully. It contains:
- **Objective**: What to accomplish
- **Specific Questions**: Numbered list of questions to answer
- **Expected Output Shape**: The EXACT structure your results must follow

Execute the work based on `task_type`:

- **research**: Use web search to find information, compare options, gather data
- **data_gathering**: Collect specific data points from known or discoverable sources
- **analysis**: Analyze provided context and produce insights
- **validation**: Verify claims, check facts, validate assumptions

**Rules during execution**:
- Use web search and documentation lookup freely
- Read project files listed in `context.relevant_files` if needed
- **DO NOT** modify any source code files
- **DO NOT** run project code or install packages
- **DO NOT** modify `.claude/manifest.yaml`

### Step 7: Deliver Results

Create the delivery file at the exact path specified in the task's `delivery.target` + `delivery.target_filename`. Typically this is `.claude/remediation/inbox/`.

The delivery file **MUST** start with this YAML frontmatter:

```yaml
---
id: "{id from task}"
source: "external_research"
severity: "low"
created: "{current ISO timestamp}"
context: "{one-line summary of what was researched}"
commissioned_by: "{commissioner from task}"
task_type: "{task_type from task}"
delivery_format: "{delivery.format from task}"
---
```

Below the frontmatter, write the results in **EXACTLY** the structure from the task's "Expected Output Shape" section:

- If `delivery.format` is `yaml`: wrap results in a ```yaml code fence
- If `delivery.format` is `markdown`: write results as markdown prose with headers
- If `delivery.format` is `json_in_markdown`: wrap results in a ```json code fence

Write the file using the terminal:

```bash
cat > .claude/remediation/inbox/OBX-001_external_research_2026-02-11.md << 'DELIVERY_EOF'
---
id: "OBX-001"
source: "external_research"
...frontmatter...
---

...results...
DELIVERY_EOF
```

### Step 8: Mark Complete

Move the task file from `active/` to `completed/`:

```bash
mv .claude/outbox/active/OBX-001_research_2026-02-11.md .claude/outbox/completed/OBX-001_research_2026-02-11.md
```

Edit the file: set `status: "completed"` and append:

```yaml
completed_at: "{ISO timestamp}"
delivery_file: ".claude/remediation/inbox/OBX-001_external_research_2026-02-11.md"
items_returned: {count}
executor: "antigravity/gemini-3"
```

Report: **"Completed task {id}. Delivered {N} items to {delivery path}."**

### Step 9: Check for More

Run the discovery script again:

```bash
bash .agent/skills/outbox-poller/scripts/check_outbox.sh .
```

If more tasks exist, ask: **"There are {N} more pending tasks. Process the next one?"**

---

## Critical Rules

1. **NEVER modify source code** in the project repository
2. **NEVER update manifest.yaml** or any `.claude/` governance files
3. **NEVER create branches, commits, or pull requests**
4. **ALWAYS deliver in the exact format specified** by the task's Expected Output Shape
5. **ALWAYS include sources** (URLs, documentation references) in your results
6. **ALWAYS set `source: "external_research"`** in delivery frontmatter
7. **If you cannot fulfil a task**, move it to `rejected/` with a clear reason — do not deliver partial or speculative results
8. **One task at a time** — complete or reject the current task before picking up another

## Error Handling

| Scenario | Action |
|----------|--------|
| `pending/` directory doesn't exist | Report "No outbox directory found" and stop |
| Task file has malformed frontmatter | Move to `rejected/` with reason "Malformed frontmatter" |
| Cannot access web for research task | Move to `rejected/` with reason "Web access unavailable" |
| Results exceed `delivery.max_items` | Truncate to max and note truncation in `summary` |
| Task type is unrecognized | Move to `rejected/` with reason "Unknown task type: {type}" |
