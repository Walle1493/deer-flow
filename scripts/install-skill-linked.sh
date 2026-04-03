#!/usr/bin/env bash
# Install a skill with npx skills (project-local .agents/skills) and symlink into skills/custom
# so DeerFlow's loader sees it. Resolves repo root via deer-flow.code-workspace.
#
# Usage:
#   ./scripts/install-skill-linked.sh inferen-sh/skills@web-search
#   ./scripts/install-skill-linked.sh https://github.com/org/repo --skill feishu-lark
#
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <owner/repo@skill-name> [npx skills add args...]" >&2
  echo "   or: $0 <repo-url> --skill <name> [other npx args...]" >&2
  exit 1
fi

find_project_root() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/deer-flow.code-workspace" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo ""
  return 1
}

PROJECT_ROOT="$(find_project_root)"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Error: could not find project root (deer-flow.code-workspace)." >&2
  exit 1
fi

cd "$PROJECT_ROOT"

SKILL_NAME=""
if [[ "$1" == *"@"* ]]; then
  SKILL_NAME="${1##*@}"
else
  prev=""
  for arg in "$@"; do
    if [[ "$prev" == "--skill" ]]; then
      SKILL_NAME="$arg"
      break
    fi
    prev="$arg"
  done
fi

if [[ -z "$SKILL_NAME" || "$SKILL_NAME" == *"/"* || "$SKILL_NAME" == *".."* ]]; then
  echo "Error: could not derive a valid skill name (use owner/repo@skill or --skill <name>)." >&2
  exit 1
fi

has_agent=0
has_yes=0
for arg in "$@"; do
  [[ "$arg" == "--agent" ]] && has_agent=1
  [[ "$arg" == "-y" || "$arg" == "--yes" ]] && has_yes=1
done

npx_args=("$@")
[[ "$has_agent" -eq 0 ]] && npx_args+=(--agent universal)
[[ "$has_yes" -eq 0 ]] && npx_args+=(-y)

echo "Running: npx skills add ${npx_args[*]}"
npx skills add "${npx_args[@]}"

SKILL_SOURCE="$PROJECT_ROOT/.agents/skills/$SKILL_NAME"
if [[ ! -d "$SKILL_SOURCE" ]]; then
  echo "Error: skill not found at $SKILL_SOURCE" >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/skills/custom"
ln -sfn "$SKILL_SOURCE" "$PROJECT_ROOT/skills/custom/$SKILL_NAME"
echo "Linked: skills/custom/$SKILL_NAME -> $SKILL_SOURCE"
echo "Restart DeerFlow if the skills list does not refresh."
