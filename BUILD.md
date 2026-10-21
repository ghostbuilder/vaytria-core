# Build and verify

The full implementation is reproducible from Bitcoin Core commit
`9be056a8a72b624dae9623b2f7bded92c2a21c91` plus `network/source.patch`.
The included preparation script checks the upstream commit and exact patch hash.
No wallet data or private development chain is needed.

## Linux x86_64, Ubuntu 24.04

Install Git, GCC/G++ 13+, CMake, Ninja, pkg-config, libevent-dev, libboost-dev and
libsqlite3-dev. From this repository:

```sh
python3 scripts/prepare-source.py
cmake -S core -B core/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=OFF -DENABLE_IPC=OFF -DWITH_ZMQ=OFF -DENABLE_WALLET=ON -DBUILD_TESTS=ON -DBUILD_BENCH=OFF
cmake --build core/build --parallel 2
ctest --test-dir core/build --output-on-failure --parallel 2
python3 scripts/test-client.py --daemon core/build/bin/bitcoind
python3 scripts/package.py --platform linux-x86_64 --bin-dir core/build/bin
```

## Native Windows x64

Use Visual Studio 2026 18.3+ with Desktop development with C++, its CMake/vcpkg
tools and Python 3. Open Developer PowerShell for that installation, set
`VCPKG_ROOT` to the vcpkg checkout and run:

```powershell
python scripts/prepare-source.py
cmake -S core -B core/build --preset vs2026-static -DBUILD_GUI=OFF -DENABLE_IPC=OFF -DWITH_ZMQ=OFF -DENABLE_WALLET=ON -DBUILD_TESTS=ON -DBUILD_BENCH=OFF -DVCPKG_MANIFEST_NO_DEFAULT_FEATURES=ON '-DVCPKG_MANIFEST_FEATURES=wallet;tests'
cmake --build core/build --config Release --parallel 2
ctest --test-dir core/build --build-config Release --output-on-failure --parallel 2
python scripts/test-client.py --daemon core/build/bin/Release/bitcoind.exe
python -m pip install pyinstaller==6.22.3
python -m PyInstaller --clean --noconfirm --onefile --name vaytria --distpath frozen client/vaytria.py
python scripts/package.py --platform win64 --bin-dir core/build/bin/Release --frozen-client frozen/vaytria.exe
```

The public workflow uses standard hosted build machines. It builds software and
tests only isolated regtest chains; it does not mine live coins or host a live
network. There are no deployment credentials or wallet secrets in the workflow.
Windows release binaries are unsigned. Review source, build provenance and
checksums; no instructions disable antivirus, certificate checks or OS protections.
