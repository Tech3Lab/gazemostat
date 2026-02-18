#!/usr/bin/env python3
"""
Generate an XGBoost model that returns a single vector output.

Output structure (float values in [0..1]):
- 4 values for global results: G_val1..G_val4
- then 4 values per task slot: T1_val1..T1_val4, ..., T10_val1..T10_val4
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

# Generate random targets (0-1 range) for multiple tasks + global results
n_tasks = 10  # Support up to 10 tasks
n_values_per_page = 4
n_outputs = (n_tasks + 1) * n_values_per_page  # 4 global + 4 per task slot
y_train = np.random.rand(n_samples, n_outputs).astype(np.float32)

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
output_structure = [f"G_val{i+1}" for i in range(n_values_per_page)]
for t in range(1, n_tasks + 1):
    output_structure += [f"T{t}_val{i+1}" for i in range(n_values_per_page)]

metadata = {
    "n_features": n_features,
    "n_tasks": n_tasks,
    "output_format": "vector",
    "output_structure": output_structure,
    # UI/inference timing hints for the app (used to display ETA/progress).
    "estimated_seconds_per_value": 3,
    "n_values_per_page": n_values_per_page,
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
print("Output format: [G_val1..G_val4, T1_val1..T1_val4, ..., T10_val1..T10_val4]")
print(f"Total outputs: {n_outputs} (4 global + {n_tasks} tasks x 4)")

