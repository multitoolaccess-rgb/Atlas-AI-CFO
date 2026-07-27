#!/usr/bin/env bash
# scripts/setup-github-auth.sh
#
# Configures authentication with GitHub so that `git push github`
# (and the post-commit auto-push hook) works.
#
# Three options are supported:
#   1. HTTPS with a Personal Access Token (PAT) — easiest on first use
#   2. SSH key — best long-term
#   3. GitHub CLI — interactive, handles PAT/SSH for you

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "🔐 GitHub Authentication Setup"
echo "=========================================="
echo ""

GITHUB_URL=$(git remote get-url github 2>/dev/null || true)
if [ -z "$GITHUB_URL" ]; then
  echo "❌ No 'github' remote found. Add it first with:"
  echo "   git remote add github https://github.com/<user>/<repo>.git"
  exit 1
fi

# Extract host/path from the remote URL so we can rebuild HTTPS/SSH URLs
# regardless of whether the remote is currently HTTPS or SSH.
REMOTE_PATH=""
case "$GITHUB_URL" in
  git@github.com:*)
    REMOTE_PATH=${GITHUB_URL#git@github.com:}
    ;;
  https://*)
    REMOTE_PATH=${GITHUB_URL#https://}
    REMOTE_PATH=${REMOTE_PATH#*/}
    ;;
  *)
    REMOTE_PATH=""
    ;;
esac

if [ -z "$REMOTE_PATH" ]; then
  echo "❌ Could not parse the 'github' remote URL: $GITHUB_URL"
  echo "   Make sure it looks like: https://github.com/<user>/<repo>.git"
  exit 1
fi

echo "Your repo is configured to push to: $GITHUB_URL"
echo ""

# If running non-interactively, print instructions and exit
if [ ! -t 0 ]; then
  cat <<'EOF'
This script is interactive. Run it from a terminal and choose an option.

Quick reference:

1. HTTPS with PAT:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: repo (full control)
   - Copy the token
   - Run: git push github main
   - When prompted, enter your GitHub username and the token as the password

2. SSH key:
   - Generate a key: ssh-keygen -t ed25519 -C "your-email@example.com"
   - Add the public key to https://github.com/settings/keys
   - Change the remote URL: git remote set-url github git@github.com:<user>/<repo>.git
   - Test: ssh -T git@github.com

3. GitHub CLI:
   - Install: https://cli.github.com
   - Run: gh auth login
   - Then: gh repo fork --clone=false (if needed)

EOF
  exit 0
fi

echo "Choose an authentication method:"
echo "  1) HTTPS with Personal Access Token (PAT) — recommended for quick setup"
echo "  2) SSH key — recommended for long-term use"
echo "  3) GitHub CLI — interactive, handles auth for you"
echo ""

read -rp "Enter choice (1/2/3): " choice

case "$choice" in
  1)
    echo ""
    echo "📋 HTTPS with PAT setup:"
    echo "  1. Go to https://github.com/settings/tokens"
    echo "  2. Click 'Generate new token (classic)'"
    echo "  3. Select scope: repo (full control)"
    echo "  4. Copy the token"
    echo ""
    echo "⚠️  Security note: do NOT paste the token into the remote URL."
    echo "   Git will prompt for it on the first push and the credential"
    echo "   helper can cache it securely."
    echo ""
    git remote set-url "github" "https://github.com/${REMOTE_PATH}"
    echo "✅ Remote updated to use HTTPS."
    echo ""
    echo "💡 To cache credentials on macOS, run:"
    echo "     git config --global credential.helper osxkeychain"
    echo ""
    echo "🧪 Test with: git push github main"
    ;;
  2)
    echo ""
    echo "📋 SSH key setup:"
    if [ ! -f "$HOME/.ssh/id_ed25519.pub" ] && [ ! -f "$HOME/.ssh/id_rsa.pub" ]; then
      echo "  1. Generate a key: ssh-keygen -t ed25519 -C \"your-email@example.com\""
      echo "  2. Add the public key to https://github.com/settings/keys"
    else
      echo "  ✅ SSH key already exists."
      echo "  1. Add the public key to https://github.com/settings/keys"
    fi
    git remote set-url "github" "git@github.com:${REMOTE_PATH}"
    echo "  2. Change the remote URL (done above)"
    echo "  3. Test: ssh -T git@github.com"
    ;;
  3)
    if command -v gh >/dev/null 2>&1; then
      echo ""
      echo "🔧 Running gh auth login..."
      gh auth login
      echo ""
      echo "✅ GitHub CLI authenticated."
    else
      echo ""
      echo "❌ GitHub CLI (gh) is not installed."
      echo "   Install it from https://cli.github.com and run this script again."
      exit 1
    fi
    ;;
  *)
    echo "Invalid choice. Run the script again."
    exit 1
    ;;
esac

echo ""
echo "=========================================="
echo "🧪 Testing connection to GitHub..."
if git ls-remote github --quiet 2>/dev/null; then
  echo "✅ Authentication works."
  echo ""
  echo "Push your code with:"
  echo "   git push -u github main"
else
  echo "⚠️  Could not connect to GitHub. Check your credentials and try again."
  exit 1
fi
echo "=========================================="
