# EC2 AL2023 Setup Notes

Instance: `i-0ba20b11fe498e30f` (`t3.xlarge`, 4 vCPU / 16GB)
Public IP: `34.207.240.105`
Key: `~/al2023-dev.pem`
SSH: `ssh -i ~/al2023-dev.pem ec2-user@34.207.240.105`

## What's installed

- Python 3.14.4 (via uv)
- venv at `~/scaler-env`
- `opengris-scaler==2.0.17` (editable install from `~/scaler`, branch `feat/orb-ec2-config-script`)

## Steps taken

### 1. Launch EC2 instance

```bash
# Find latest AL2023 AMI
aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023.*-x86_64" "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId'
# → ami-0c1e21d82fe9c9336 (al2023-ami-2023.11.20260413.0, kernel 6.18)

# Create key pair
aws ec2 create-key-pair --key-name al2023-dev --query 'KeyMaterial' --output text > ~/al2023-dev.pem
chmod 600 ~/al2023-dev.pem

# Create security group (SSH from current IP only)
MY_IP=$(curl -s https://checkip.amazonaws.com)
SG_ID=$(aws ec2 create-security-group --group-name al2023-ssh-access \
  --description "SSH access for AL2023 dev instance" --vpc-id vpc-d82774bd \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr "${MY_IP}/32"

# Launch t3.xlarge (first attempt was t3.micro — too slow/OOM for C++ build)
aws ec2 run-instances --image-id ami-0c1e21d82fe9c9336 --instance-type t3.xlarge \
  --key-name al2023-dev --security-group-ids sg-0049e76a05b7ca565 \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=al2023-dev}]'
```

### 2. Install system dependencies

```bash
sudo dnf install -y git gcc14 gcc14-c++ gcc14-libstdc++-devel \
  autoconf automake libtool libuv-devel
```

**Notes:**
- AL2023 ships GCC 11 by default; the codebase uses `<expected>` (C++23), requires GCC 12+. GCC 14 is available as `gcc14`/`gcc14-c++` with binaries at `/usr/bin/gcc14-gcc` and `/usr/bin/gcc14-g++`.
- `libuv-devel` installs both `libuv.a` (static, no PIC) and `libuv.so` (shared).

### 3. Install uv + Python 3.14

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv python install 3.14
```

### 4. Clone repo and checkout branch

```bash
git clone https://github.com/magniloquency/scaler.git
cd scaler
git checkout feat/orb-ec2-config-script
```

### 5. Build and install Cap'n Proto

The project vendors Cap'n Proto via `scripts/library_tool.sh`. Must pass GCC 14 explicitly or configure picks up GCC 11 (no C++14 support found without `g++` in PATH).

```bash
CC=/usr/bin/gcc14-gcc CXX=/usr/bin/gcc14-g++ bash scripts/library_tool.sh capnp download
CC=/usr/bin/gcc14-gcc CXX=/usr/bin/gcc14-g++ bash scripts/library_tool.sh capnp compile
sudo bash scripts/library_tool.sh capnp install
# Installs to /usr/local; .pc files land in /usr/local/lib/pkgconfig
```

### 6. Install opengris-scaler

```bash
~/.local/bin/uv venv --python 3.14 ~/scaler-env

PKG_CONFIG_PATH=/usr/local/lib/pkgconfig \
CMAKE_ARGS='-DCMAKE_C_COMPILER=/usr/bin/gcc14-gcc \
            -DCMAKE_CXX_COMPILER=/usr/bin/gcc14-g++ \
            -DCMAKE_DISABLE_FIND_PACKAGE_libuv=TRUE' \
  ~/.local/bin/uv pip install --python ~/scaler-env -e '.[all]'
```

**Why `PKG_CONFIG_PATH`:** capnp `.pc` files are in `/usr/local/lib/pkgconfig`, not on the default search path.

**Why `CMAKE_ARGS` compilers:** scikit-build-core spawns CMake in an isolated env; `CC`/`CXX` env vars are not forwarded. Must pass via `CMAKE_ARGS`.

**Why `DCMAKE_DISABLE_FIND_PACKAGE_libuv=TRUE`:** The `wrapper/uv/CMakeLists.txt` does `find_package(libuv QUIET)` first; if found it uses `libuv::uv_a` (static). The AL2023 `libuv.a` was not compiled with `-fPIC`, so linking into a shared `.so` fails. Disabling `find_package` forces the fallback to `pkg_check_modules(libuv)` which links against `libuv.so`.

## Usage

```bash
source ~/scaler-env/bin/activate
scaler --help
```
