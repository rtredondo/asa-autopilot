# Bug Fixes: Logging Duplication and Dashboard Guardrail Columns

## Issue 1: Logging Duplicated

### The Bug
Every log line printed twice with identical timestamps.

**Root Cause:**
```python
# log_config/__init__.py
def setup_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)  # ← No guard!
    root_logger.addHandler(file_handler)      # ← No guard!
```

The `setup_logging()` function had no check to prevent adding duplicate handlers. When called multiple times (either explicitly or by Streamlit reruns), new handlers accumulated on the root logger without removing old ones.

**Example flow:**
1. dashboard.py imports and calls `setup_logging()` → 2 handlers added (console + file)
2. Streamlit reruns script → calls `setup_logging()` again → 4 handlers total
3. Any log message gets output to all 4 handlers → prints 2x to console, 2x to file

### The Fix
Added a guard to prevent reconfiguration if handlers already exist:

```python
# log_config/__init__.py - FIXED
def setup_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    
    # Guard against duplicate handlers (important for Streamlit reruns)
    if root_logger.handlers:
        return  # Exit early if already configured
    
    # Only add handlers if none exist
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
```

**Status:** ✅ **FIXED** - Verified: second call to `setup_logging()` now returns early without adding duplicate handlers.

---

## Issue 2: Logging Level (Info vs Debug)

### The Bug
Routine cooldown checks were logged at INFO level, polluting the log with noise about routine checks that aren't decisions.

**Root Cause:**
```python
# guardrails/__init__.py - BEFORE
if not last_decision:
    logger.info(f"{entity_type} {entity_id} has no prior decisions, eligible for action")
    #           ↑ INFO level - too noisy!
```

### The Fix
Changed routine cooldown check logging from INFO to DEBUG:

```python
# guardrails/__init__.py - FIXED
if not last_decision:
    logger.debug(f"{entity_type} {entity_id} has no prior decisions, eligible for action")
    #           ↑ DEBUG level - routine check noise
```

Also changed the other two check_cooldown() log statements (cooldown expired and on cooldown) from INFO to DEBUG.

**Status:** ✅ **FIXED** - INFO level now reserved for actual decisions and guardrail blocks only.

---

## Issue 3: Dashboard Guardrail Columns ("Blocked" and "Cooldown")

### The Bugs

**Problem 1: Cooldown column always shows '3d' regardless of history**

Every visible row showed "Cooldown: 3d" even for keywords with no prior decision history.

**Root Cause:**
The `run_evaluation()` function logs ALL proposed actions to the state store (lines 141-152), regardless of guardrail status. Then immediately after, the display code recalculates cooldown from the state store:

```python
# dashboard.py - BEFORE (display code)
for action in all_actions:
    # ... after run_evaluation() has already logged all actions ...
    if action.target_type == "keyword":
        last_decision = state_store.get_last_keyword_decision(action.target_id)
    
    if last_decision:
        cooldown_expiry = last_date + timedelta(days=4)
        cooldown_days = max(0, (cooldown_expiry - datetime.utcnow()).days)
        # ↑ Since all actions were JUST LOGGED, they all have recent decisions!
        # ↑ So cooldown_days ≈ 4 for ALL of them
```

**Timeline:**
- 10:00am: Propose 213 pause actions
- 10:00am: Log all actions to state store (sets decision_date = 10:00am)
- 10:01am: Display table queries state store
- 10:01am: Finds decisions at 10:00am → calculates cooldown_expiry = 10:00am + 4 days
- 10:01am: Shows "3d" or "4d" for EVERY action (all just logged moments ago)

---

**Problem 2: Blocked column shows inconsistent values**

The "Blocked" column used `action.guardrail_blocked`, which was set at proposal time. But the dashboard's display code was recalculating cooldown from the state store AFTER logging. This created a mismatch:

- `action.guardrail_blocked` = based on checks at proposal time
- Displayed `cooldown_days` = based on state store query after logging
- If cooldown_days > 0, the action SHOULD be blocked, but `action.guardrail_blocked` might still be False!

Example:
```
Proposal time (10:00am):
  - check_cooldown() returns True (no prior decisions)
  - action.guardrail_blocked = False

Display time (10:01am after logging):
  - Query state store: finds decision logged at 10:00am
  - cooldown_days = 3
  - But action.guardrail_blocked is still False!
  - Shows "✅ No" in Blocked column, "3d" in Cooldown column ← MISMATCH!
```

---

### The Fix

**Step 1:** Store the proposal-time cooldown status on the action object during proposal:

```python
# dashboard.py - run_evaluation() - FIXED
cooldown_days_remaining = 0
# ... cooldown check logic ...
if not check_cooldown(...):
    guardrail_blocked = True
    cooldown_days_remaining = max(0, (cooldown_expiry - datetime.utcnow()).days)

action.guardrail_blocked = guardrail_blocked
action.cooldown_days_remaining = cooldown_days_remaining  # ← Store it!
```

**Step 2:** Use the stored value in the display, not recalculated values:

```python
# dashboard.py - display code - FIXED
# Use the value stored during proposal, not recalculated from state store
cooldown_days = getattr(action, 'cooldown_days_remaining', 0)
```

Instead of:
```python
# OLD - recalculated from state store AFTER logging
if last_decision:
    cooldown_expiry = last_date + timedelta(days=4)
    cooldown_days = max(0, (cooldown_expiry - datetime.utcnow()).days)
    # ← Wrong! This includes actions just logged
```

**Status:** ✅ **FIXED** - The "Blocked" and "Cooldown" columns now reflect proposal-time guardrail checks, not post-logging state store queries.

---

## What Was Actually Wrong (Plain Language)

### Logging Duplication
Every time `setup_logging()` was called, it added TWO NEW handlers (console + file) to the logger without checking if they already existed. On the second call, logs went to 4 handlers (2 old + 2 new). This is like having 4 speakers playing the same message simultaneously.

### Guardrail Columns
The dashboard was:
1. Running the decision engine → proposing actions
2. Logging ALL actions to the database
3. Immediately querying the database back to display
4. Finding that ALL actions just got logged moments ago
5. Showing "3d cooldown" for all of them (because they were logged 3-4 days from the display date)

This made the "Cooldown" column useless — it always showed ~3-4 days for everything because everything was just logged. And the "Blocked" column showed proposal-time status, not the post-logging state, creating mismatches.

---

## Verification

✅ **Test 1:** `setup_logging()` called twice → handler count stays at 2 (guard works)
✅ **Test 2:** `check_cooldown()` emits DEBUG logs, not INFO logs
✅ **Test 3:** Action objects now store `cooldown_days_remaining` at proposal time

All fixes verified and ready for production.
