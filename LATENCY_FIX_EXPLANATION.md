# Latency Fix Explanation - Fix #3

## Fix #3: Check Multiple Validity Flags

### Current Implementation

The current code uses a fallback hierarchy for gaze data validity:
1. **BPOGV** (Best POG validity) - Primary choice
2. **FPOGV** (Fixation POG validity) - Fallback if BPOGV unavailable
3. **LPOGV** (Left Eye POG validity) - Fallback if FPOGV unavailable
4. **RPOGV** (Right Eye POG validity) - Fallback if LPOGV unavailable

This is used for the `valid` flag in gaze samples (lines 556-586).

### The Problem

When a user moves away from the tracker, different validity flags may become False at different times:

1. **BPOGV/FPOGV** (gaze validity) - These use fixation filtering, which may delay detection of absence
   - The fixation filter waits to confirm the user has moved away (not just a saccade)
   - This can cause a delay of several hundred milliseconds

2. **LPUPILV/RPUPILV** (3D eye data validity) - These indicate if 3D eye position data is valid
   - These may become False faster than gaze validity flags
   - They directly indicate if the eye is detected in 3D space

3. **LPV/RPV** (2D pupil validity) - These indicate if 2D pupil detection is valid
   - These may also respond faster than fixation-filtered gaze data

### Why Fix #3 Would Help

By checking **multiple validity flags simultaneously**, we can detect absence faster:

```python
# Pseudo-code for fix #3 (not implemented)
is_absent = (
    (not bpogv and not fpogv) or  # No valid gaze
    (not lpupilv and not rpupilv) or  # No valid 3D eye data
    (not lpv and not rpv)  # No valid 2D pupil data
)
```

**Benefits:**
- **Faster detection**: If any validity flag indicates absence, we can immediately clear the display
- **More robust**: Multiple sources of truth reduce false positives/negatives
- **Better user experience**: Users see "No data" faster when they move away

### Why It's Not Implemented

Fix #3 is more complex because:

1. **Different flags have different meanings:**
   - BPOGV/FPOGV: Gaze tracking validity (includes fixation filtering)
   - LPUPILV/RPUPILV: 3D eye position validity (direct detection)
   - LPV/RPV: 2D pupil detection validity

2. **Potential for false positives:**
   - A brief blink might make LPV/RPV False temporarily, but gaze might still be valid
   - We don't want to clear the display during normal blinks

3. **Current fixes (#1, #2, #4) already address the main issue:**
   - Fix #1: Filters distance values by validity (LPUPILV/RPUPILV)
   - Fix #2: Reduces timeout from 3.0s to 0.8s
   - Fix #4: Clears values immediately when invalid
   - These three fixes together should significantly reduce latency

### When Fix #3 Would Be Beneficial

Fix #3 would be most useful if:
- You need **instantaneous** detection of absence (no delay at all)
- You're willing to accept occasional false positives (brief "No data" during blinks)
- You want the most aggressive absence detection possible

### Alternative Approach (Simpler)

Instead of implementing fix #3, we could:
- Use **LPUPILV/RPUPILV** as the primary indicator (already done in fix #1)
- These flags are more direct indicators of 3D eye detection
- They respond faster than fixation-filtered gaze data
- Combined with fixes #1, #2, and #4, this should provide good latency reduction

### Conclusion

Fix #3 is a more advanced optimization that would provide marginal additional benefit. The combination of fixes #1, #2, and #4 should already significantly reduce latency. If further reduction is needed after testing, fix #3 could be implemented as a future enhancement.
