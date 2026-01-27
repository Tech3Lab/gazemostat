# Latency Fixes - Queue Processing and Display Updates

## Problem Identified

There was significant latency between tracker interactions and data display due to several bottlenecks:

1. **Limited Queue Processing**: Only 2 samples per frame at 30 FPS = maximum 60 samples/second processing rate
   - If the tracker sends data at 60 Hz or higher, samples accumulate in the queue
   - Queue buildup causes increasing latency over time

2. **Low Display Refresh Rate**: 30 FPS adds ~33ms of display latency
   - Each frame takes ~33ms, so data can be up to 33ms old before being displayed

3. **Queue Accumulation**: When samples arrive faster than they're processed, latency builds up
   - Queue has maxsize=1024, which can buffer over 17 seconds of data at 60 Hz

## Fixes Applied

### Fix #1: Process All Available Samples Per Frame
**Location**: `main.py` lines 2038-2065

**Before**:
```python
for _ in range(2):  # Only process 2 samples per frame
    s = gp.q.get_nowait()
    # ... process sample
```

**After**:
```python
samples_processed = 0
max_samples_per_frame = 100  # Safety limit
while samples_processed < max_samples_per_frame:
    s = gp.q.get_nowait()
    samples_processed += 1
    # ... process sample
```

**Impact**: 
- Processes all available samples up to 100 per frame (safety limit)
- Prevents queue buildup by keeping up with incoming data rate
- Ensures latest data is always used for display

### Fix #2: Increase Display Refresh Rate
**Location**: `main.py` line 36

**Before**:
```python
FPS = 30
```

**After**:
```python
FPS = 60  # Increased from 30 to reduce display latency
```

**Impact**:
- Reduces display latency from ~33ms to ~16ms
- Smoother visual updates
- Better responsiveness to user interactions

### Fix #3: Queue Size Monitoring
**Location**: `main.py` lines 2038-2070

**Added**:
```python
queue_size_before = gp.q.qsize()  # Monitor queue size
# ... process samples ...
queue_size_after = gp.q.qsize()

if queue_size_before > 50:  # Threshold for warning
    print(f"Warning: Queue size is {queue_size_before} samples...")
```

**Impact**:
- Helps diagnose latency issues during development
- Warns when queue is building up (indicates processing can't keep up)
- Provides visibility into system performance

## Expected Results

After these fixes:
- **Reduced Display Latency**: From ~33ms to ~16ms (50% reduction)
- **Eliminated Queue Buildup**: All available samples processed each frame
- **Better Responsiveness**: Latest data always displayed immediately
- **Improved Monitoring**: Queue size warnings help diagnose issues

## Additional Notes

1. **Safety Limit**: The `max_samples_per_frame = 100` limit prevents a single frame from blocking too long if the queue is very large. In normal operation, all samples should be processed.

2. **Display Updates**: Even though we process all samples, we only keep the latest sample for display purposes. This reduces processing overhead while ensuring the most recent data is shown.

3. **Collection Mode**: When `state == "COLLECTING"`, all samples are still appended to `gaze_samples` for later analysis, so no data is lost.

4. **Performance**: Processing all samples per frame is efficient because:
   - Queue operations are fast (O(1) for get_nowait)
   - Sample processing is lightweight (just extracting values)
   - Only the latest sample is used for display calculations

## Testing Recommendations

1. **Monitor Queue Size**: Watch for queue size warnings in console output
2. **Check Frame Rate**: Verify the display runs at 60 FPS (use pygame's clock.get_fps())
3. **Test with Real Tracker**: Ensure latency is reduced with actual hardware
4. **Verify No Data Loss**: Confirm all samples are processed during collection

## Future Optimizations (If Needed)

If latency is still an issue after these fixes:

1. **Non-blocking Socket**: Use `sock.setblocking(False)` with select/poll for non-blocking I/O
2. **Separate Thread for Display**: Process queue in background thread, update display separately
3. **Reduce Feature Window**: If using real-time analysis, reduce `FEATURE_WINDOW_MS` from 1500ms
4. **Optimize Display Rendering**: Profile and optimize drawing operations if needed
