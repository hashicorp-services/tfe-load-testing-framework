# Known Limitations

This document describes known limitations of the TFE Load Testing Framework, particularly when running against local development environments.

## Local Development Environment Limitations

### State Download 401 Errors (Fixed)

**Status:** Fixed in current version

**Root Cause (was a code bug):**

The `hosted-state-download-url` attribute returned by the TFE API is a TFE endpoint
(`/api/v2/...`) that requires a `Bearer` token, which TFE then redirects internally to
object storage. It is **not** a bare presigned URL.

The download tasks were creating a bare `requests.Session()` with no `Authorization`
header, so TFE rejected every request with 401 before the redirect could occur.

**Fix:**

Both `download_current_state` and `download_specific_version` now use `self.client.get()`
(the Locust HTTP session, which carries the `Authorization: Bearer` header) and extract
the URL path via `urlparse` so the request routes correctly through the Locust base URL.

**All state download operations now work at 100% success rate against any TFE instance.**

### Sentinel Engine Duration Can Show 0ms

**Status:** Known limitation - Local TFE environment behavior

**Affected Operations:**
- Sentinel engine-duration tracking from Policy Checks API payloads
- Local/sample-policy performance calibration

**Symptoms:**
- Policy evaluations complete successfully.
- Policy pass/fail counts, soft-mandatory overrides, and policy-check statuses are accurate.
- TFE can return `0` for all engine-duration fields in the Policy Checks API result payload.
- `policy_stage_wall_time_ms` remains available and should be used as the primary load-test latency metric.

**Root Cause:**

In the verified local TFE environment, TFE persisted `0` for Sentinel result duration fields before the API response was serialized. This was confirmed in the local PostgreSQL database:

```sql
select count(*) total,
       count(*) filter (where duration_ms = 0) zero_duration,
       min(duration_ms) min_ms,
       max(duration_ms) max_ms
from rails.policy_results;
```

In that local run, all rows had `duration_ms = 0`. The stored Sentinel result payload also had zeroes in the aggregate and per-policy fields:

```json
{
  "result": {
    "duration-ms": 0,
    "sentinel": {
      "data": {
        "": {
          "duration": 0,
          "policies": [
            {
              "duration": 0,
              "policy": {...},
              "result": true
            }
          ]
        }
      }
    }
  }
}
```

Task-worker logs showed the Sentinel worker evaluating the sample policies and requesting the internal callback in the same millisecond. The callback itself took tens of milliseconds, but that work is not included in the policy result's `duration-ms` field.

This means the zero value is not caused by Locust parsing. It is the value TFE stores for the Sentinel engine evaluation result. For very small policies, the measured engine-only evaluation can be below the integer-millisecond reporting floor, and the nested `sentinel` payload can mirror that same zero duration. HashiCorp's Policy Checks API examples also show `"duration-ms": 0`, and the docs warn that the nested `sentinel` hash is low-level policy engine output whose structure may change.

**Impact:**

- ✅ **Policy evaluations**: Pass/fail/override workflows remain functional.
- ✅ **Policy check status**: `passed`, `soft_failed`, `hard_failed`, and `overridden` statuses remain reliable.
- ✅ **Pass/fail statistics**: Counts are derived from policy-check results and remain useful.
- ✅ **`policy_stage_wall_time_ms`**: Available as the primary user-visible policy-stage latency metric.
- ❌ **Engine duration metrics**: May be unavailable when TFE returns `0` for every engine-duration field.

**Workarounds:**

1. **Use `policy_stage_wall_time_ms` for local and customer-facing latency**
   - The framework computes this from Policy Checks API `status-timestamps`, with observed polling timestamps as a fallback.
   - This includes queueing, orchestration, Sentinel evaluation, callback completion, and override progression when applicable.
   - The framework emits it as a Locust metric named `policy_stage_wall_time_ms`.

2. **Use the synthetic-heavy profile for calibration**
   - This is the default for `./examples/run_sentinel_policy_test.sh` and `task test:sentinel`.
   - It creates/reuses `loadtest-policies-synthetic-heavy` with an additional advisory policy that repeatedly scans plan changes.
   - It can make local policy stages more visible, but it is intentionally artificial.
   - Tune it with `TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT` and `TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT`.

3. **Accept the limitation for local testing**
   - Use the local environment for policy logic, setup idempotency, pass/fail behavior, overrides, and monitoring plumbing.
   - Treat engine duration as best effort in local/sample-policy runs.

4. **Test against a representative TFE deployment**
   - Validate whether non-trivial customer policies and the target TFE version populate non-zero durations.
   - Prefer real policy sets over synthetic sample policies when capacity planning or customer benchmarking matters.

**Verification:**

The duration extraction code checks all possible duration field locations:

```python
# Option 1: Direct duration-ms field
if 'duration-ms' in result:
    duration_ms = result['duration-ms']  # Returns 0 in local env

# Option 2: Sentinel data with nanoseconds
elif 'sentinel' in result:
    for policy in workspace_data.get('policies', []):
        duration_ns += policy.get('duration', 0)  # Returns 0 in local env

# Option 3: Direct duration field (seconds to ms)
elif 'duration' in result:
    duration_ms = result['duration'] * 1000  # Returns 0 in local env
```

All fields are checked correctly. The issue is that local TFE can store and return zero for these policy results.

**Related API Note:**

HashiCorp's [Policy Checks API](https://developer.hashicorp.com/terraform/enterprise/api-docs/policy-checks) is the legacy Sentinel workflow. The current API docs state that policy checks support Sentinel versions up to 0.40.x and recommend policy evaluations for newer workflows. They also warn that the nested `sentinel` result hash is low-level engine detail and should be used cautiously.

The [Policy Evaluations API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/policy-evaluations) exposes task-stage policy evaluations and policy-set outcomes for newer policy workflows. Its documented response model is useful for future OPA/enhanced-policy support, but it does not provide a direct replacement for Sentinel `result.duration-ms`. For Sentinel load testing, keep Policy Checks for Sentinel outcome data and use `policy_stage_wall_time_ms` as the primary performance metric.

---

**Last Updated:** 2026-05-22  
**Affects:** Local development environment only  
**Severity:** Low (`policy_stage_wall_time_ms` workaround available)
