# Windows Installation Guide

## Prerequisites for Fresh Windows Install

### 1. Install Microsoft Visual C++ Build Tools (Required)

On a fresh Windows installation, Python packages with C extensions (like `numpy`, `xgboost`) need Microsoft Visual C++ Build Tools to compile.

**Download and install:**
- **Option A (Recommended)**: Install "Microsoft C++ Build Tools"
  - Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
  - During installation, select "Desktop development with C++" workload
  - This includes the MSVC compiler needed for building Python packages

- **Option B (Lighter)**: Install "Microsoft Visual C++ Redistributables"
  - Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
  - This is the runtime library (may not be enough for building)

### 2. Upgrade pip, setuptools, and wheel first

Before installing requirements, upgrade the build tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

### 3. Install Requirements

After installing the build tools:

```bash
# For runtime
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt
```

## Alternative: Use Pre-built Wheels (No Compilation)

If you want to avoid building from source, ensure pip uses pre-built wheels:

```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install with --only-binary flag to force pre-built wheels
pip install --only-binary :all: -r requirements.txt
```

## Troubleshooting

### If you still get distutils errors:

1. **Verify setuptools is installed:**
   ```bash
   pip install --upgrade setuptools
   python -c "import distutils; print('distutils available')"
   ```

2. **Check Python version:**
   ```bash
   python --version
   ```
   - Python 3.12+ requires setuptools for distutils
   - Python 3.11 and earlier include distutils natively

3. **Install build tools in correct order:**
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

### If packages fail to build:

- Ensure Microsoft C++ Build Tools are installed (see step 1)
- Try installing packages one at a time to identify which one fails:
  ```bash
  pip install pygame
  pip install numpy
  pip install xgboost
  ```

## Quick Start (All-in-One)

```bash
# 1. Install Microsoft C++ Build Tools first (manual download required)
#    https://visualstudio.microsoft.com/visual-cpp-build-tools/

# 2. Then run these commands:
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

