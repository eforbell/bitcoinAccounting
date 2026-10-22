#!/usr/bin/env bash
# Upgrade pip before it makes any unverified-index requests with an affected CA bundle.
# Wheel URL and SHA-256: https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576
set -euo pipefail

PYTHON="${1:-.venv/bin/python}"
if "$PYTHON" - <<'PY'
from importlib.metadata import PackageNotFoundError, version
import re
import sys

try:
    current = version("pip")
except PackageNotFoundError:
    current = ""
match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", current)
sys.exit(0 if match and tuple(int(part or 0) for part in match.groups()) >= (26, 2, 2) else 1)
PY
then
  exit 0
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
  # ensurepip's bundled wheel is offline; replace it before any index access.
  "$PYTHON" -m ensurepip --upgrade
fi

"$PYTHON" -m pip install --disable-pip-version-check --no-deps --upgrade \
  'pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70'
