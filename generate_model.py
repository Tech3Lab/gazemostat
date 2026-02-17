#!/usr/bin/env python3
"""
Generate an XGBoost model that returns a single vector output.
First element: global score
Remaining elements: scores for each task (T1, T2, ..., T10)
"""
import os
import numpy as np
import xgboost as xgb
from sklearn.multioutput import MultiOutputRegressor

# Create models directory if it doesn't exist
os.makedirs("models", exist_ok=True)

# Generate synthetic training data
# Features: mean_gaze_x, mean_gaze_y, gaze_variance_x, gaze_variance_y,
#           blink_count, fixation_duration, saccade_rate, task_duration, etc.
n_samples = 1000
n_features = 20  # Number of features the model expects

# Generate random features
X_train = np.random.rand(n_samples, n_features).astype(np.float32)

# Generate random targets (0-1 range) for multiple tasks + global score
# Output vector format: [global_score, T1_score, T2_score, ..., T10_score]
n_tasks = 10  # Support up to 10 tasks
y_train = np.random.rand(n_samples, n_tasks + 1).astype(np.float32)  # +1 for global score

# Create XGBoost model with MultiOutputRegressor to predict all outputs at once
# Output vector: [global_score, T1, T2, ..., T10]
base_model = xgb.XGBRegressor(
    n_estimators=10,
    max_depth=3,
    learning_rate=0.1,
    random_state=42,
    objective='reg:squarederror'
)

# Wrap with MultiOutputRegressor to handle multiple outputs
model = MultiOutputRegressor(base_model)
model.fit(X_train, y_train)

# Save the model
# Note: MultiOutputRegressor saves as a collection of models
# We'll save it using pickle or joblib, but XGBoost's save_model won't work directly
# Let's use joblib to save the entire MultiOutputRegressor
import joblib
joblib.dump(model, "models/model.xgb")

# Save metadata about the model
import json
metadata = {
    "n_features": n_features,
    "n_tasks": n_tasks,
    "output_format": "vector",
    "output_structure": ["global_score", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"],
    # UI/inference timing hints for the app (used to display ETA/progress).
    "estimated_seconds_per_value": 3,
    "n_values_per_page": 4,
    "feature_names": [
        "mean_gaze_x", "mean_gaze_y", "gaze_variance_x", "gaze_variance_y",
        "blink_count", "fixation_duration", "saccade_rate", "task_duration",
        "gaze_std_x", "gaze_std_y", "pupil_mean", "pupil_std",
        "validity_rate", "gaze_range_x", "gaze_range_y", "gaze_velocity_mean",
        "gaze_velocity_std", "fixation_count", "saccade_count", "total_samples"
    ]
}
with open("models/model_metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

print("Model generation complete!")
print(f"Saved model to models/model.xgb")
print(f"Output format: [global_score, T1, T2, ..., T10]")
print(f"Total outputs: {n_tasks + 1} (1 global + {n_tasks} tasks)")

