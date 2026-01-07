# Windows Setup Guide for OpenLaunch Rust

## Prerequisites

You need two things to build the Rust project on Windows:
1. **Rust toolchain** (rustc, cargo)
2. **C compiler** (for native dependencies like serialport)

## Step 1: Install Rust

### Option A: Using rustup (Recommended)

1. Download rustup-init from: https://rustup.rs/
   - Or run in PowerShell:
   ```powershell
   Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile rustup-init.exe
   ```

2. Run `rustup-init.exe`
   - Press Enter to proceed with default installation
   - This installs Rust to `%USERPROFILE%\.cargo\bin`

3. **Restart your terminal** after installation

4. Verify installation:
   ```powershell
   cargo --version
   rustc --version
   ```

### Option B: Using WSL (Windows Subsystem for Linux)

If you have WSL installed:

```bash
# In WSL terminal
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
cargo --version
```

Then build in WSL:
```bash
cd /mnt/z/openlaunch
cargo build --release
```

## Step 2: Install C Compiler

### Option 1: Microsoft C++ Build Tools (Recommended for Windows)

1. Download **Build Tools for Visual Studio**:
   - https://visualstudio.microsoft.com/visual-cpp-build-tools/
   - Or direct link: https://aka.ms/vs/17/release/vs_buildtools.exe

2. Run the installer and select:
   - ✅ **C++ build tools** workload
   - ✅ **Windows 10/11 SDK** (latest)
   - ✅ **MSVC v143 - VS 2022 C++ x64/x86 build tools**

3. **Restart your terminal** after installation

4. Verify (May need to add `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64` to env variables path. Ensure version `14.44.35207` is correct to your path):
   ```powershell
   where cl
   ```

### Option 2: Full Visual Studio

1. Download **Visual Studio Community** (free):
   - https://visualstudio.microsoft.com/downloads/

2. During installation, select:
   - ✅ **Desktop development with C++** workload

3. Restart terminal and verify

### Option 3: MinGW-w64 (Alternative)

1. Install **MSYS2**: https://www.msys2.org/

2. In MSYS2 terminal:
   ```bash
   pacman -Syu
   pacman -S mingw-w64-x86_64-gcc
   ```

3. Add to PATH:
   - Add `C:\msys64\mingw64\bin` to system PATH
   - Or use: `C:\msys64\usr\bin`

4. Configure Rust for GNU toolchain:
   ```powershell
   rustup toolchain install stable-x86_64-pc-windows-gnu
   rustup default stable-x86_64-pc-windows-gnu
   ```

## Step 3: Build the Project

Once both are installed:

```powershell
# Navigate to Rust directory
cd Z:\openlaunch\rust

# Build release version
cargo build --release

# Or run directly
cargo run --release -- --mock
```

## Troubleshooting

### "cargo: command not found"
- Rust isn't installed or not in PATH
- Restart terminal after installing Rust
- Check PATH includes: `%USERPROFILE%\.cargo\bin`

### "linker `cc` not found"
- C compiler isn't installed
- Install Microsoft C++ Build Tools (Option 1 above)
- Restart terminal after installation

### "error: could not find `link.exe`"
- MSVC tools not properly installed
- Try running from "Developer Command Prompt for VS"
- Or ensure PATH includes Visual Studio tools

### Build works but can't find serial port
- This is expected if you don't have the radar hardware
- Use `--mock` flag to test without hardware:
  ```powershell
  cargo run --release -- --mock
  ```

## Quick Test (Mock Mode)

Once everything is installed, test without hardware:

```powershell
cargo run --release -- --mock --live
```

This should:
1. Build the project
2. Run in mock mode
3. Auto-generate test shots every 5 seconds
4. Display shot metrics

## Alternative: Use WSL

If Windows build tools are problematic, use WSL:

```bash
# In WSL
sudo apt update
sudo apt install build-essential
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

cd /mnt/z/openlaunch/rust
cargo build --release
cargo run --release -- --mock
```

WSL typically has fewer build tool issues than native Windows.

