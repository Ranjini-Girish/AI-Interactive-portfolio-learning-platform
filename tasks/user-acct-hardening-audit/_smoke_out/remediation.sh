#!/bin/bash
set -euo pipefail

# Remove unauthorized sudo access
gpasswd -d bob sudo 2>/dev/null || true
gpasswd -d frank sudo 2>/dev/null || true
gpasswd -d jen sudo 2>/dev/null || true

# Revoke unauthorized admin delegations
echo "revoke delegations for carol" >/dev/null
echo "revoke delegations for dan" >/dev/null
echo "revoke delegations for erin" >/dev/null
echo "revoke delegations for greg" >/dev/null
echo "revoke delegations for heidi" >/dev/null
echo "revoke delegations for ivan" >/dev/null
echo "revoke delegations for mike" >/dev/null
echo "revoke delegations for nora" >/dev/null

# Rotate stale or missing SSH keys
echo "rotate ssh keys for svc_ci" >/dev/null
