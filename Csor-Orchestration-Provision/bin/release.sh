#!/bin/bash

set -eo pipefail

confirm_tag() {
  while true; do
    echo -n "$1 [y/n]: "
    read -r VALUE
    case "$VALUE" in
      y) return 0;;
      n) return 1;;
      *) echo "Please answer 'y' or 'n'.";;
    esac
  done
}

# Move all lines under '## [Unreleased]' into a new '## [<version>]' block
insert_changelog_version() {
  local version="$1"
  local changelog="CHANGELOG.md"

  # Determine previous version (latest semver tag)
  local previous_version
  previous_version=$(git tag -l | grep -E "^[0-9]+\.[0-9]+\.[0-9]+$" | sort -V -r | head -1)

  local repository
  repository=$(basename "$(git rev-parse --show-toplevel)")
  local compare_line="(https://github.com/PayPal-Braintree/${repository}/compare/${previous_version}...${version})"

  local tmp
  tmp=$(mktemp)
  local in_unreleased=false
  local inserted=false
  local captured=()

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^##\ \[Unreleased\][[:space:]]*$ ]]; then
      echo "$line" >> "$tmp"
      echo "" >> "$tmp"  # Add blank line after [Unreleased]
      in_unreleased=true
      continue
    fi

    if $in_unreleased; then
      if [[ "$line" =~ ^##\  ]]; then
        # Remove ALL empty lines from captured content
        local filtered_content=()
        for captured_line in "${captured[@]}"; do
          if [[ ! "$captured_line" =~ ^[[:space:]]*$ ]]; then
            # Fix formatting: ensure proper spacing for list items
            if [[ "$captured_line" =~ ^-[^[:space:]] ]]; then
              # Add space after dash if missing (e.g., "-Test 3" becomes "- Test 3")
              captured_line="${captured_line:0:1} ${captured_line:1}"
            fi
            filtered_content+=("$captured_line")
          fi
        done

        if (( ${#filtered_content[@]} == 0 )); then
          echo "No content under [Unreleased]; aborting release."
          rm -f "$tmp"
          exit 1
        fi

        echo "## [$version]$compare_line" >> "$tmp"
        for l in "${filtered_content[@]}"; do
          echo "$l" >> "$tmp"
        done
        echo "" >> "$tmp"  # Will add blank line after the version content

        in_unreleased=false
        inserted=true

        echo "$line" >> "$tmp"
        continue
      else
        captured+=("$line")
        continue
      fi
    fi
    echo "$line" >> "$tmp"
  done < "$changelog"

  mv "$tmp" "$changelog"
}

echo "Starting semver release process..."

# Ensure we have a clean branch
# if [[ -n $(git status -s) ]]; then
#   echo "Unclean branch. Please clean up before releasing"
#   exit 1
# fi

# Extract the latest semver version from git tags (format: X.Y.Z)
current_version=$(git tag -l | grep -E "^[0-9]+\.[0-9]+\.[0-9]+$" | sort -r --version-sort | head -1) || true

# tag: major.minor.patch
if [[ -z "$current_version" ]]; then
  echo "No existing semver tag found. Starting at 0.1.0."
  new_version="0.1.0"
  # Prompt for confirmation before proceeding
  if ! confirm_tag "Create and tag git repository with new version: ${new_version}?"; then
    echo -e "\nNo version change. Thank you!"
    exit 0
  fi
else
  echo "Found existing version: $current_version"
  IFS='.' read -r major minor patch <<< "$current_version"
  
  if confirm_tag "Is this a major version update?"; then
    major=$((major + 1)); minor=0; patch=0;
  elif confirm_tag "Is this a minor version update?"; then
    minor=$((minor+1)); patch=0;
  elif confirm_tag "Is this a patch update?"; then
    patch=$((patch+1));
  else
    echo -e "\nVersion update must be major, minor or patch"
    exit 0
  fi
  new_version="$major.$minor.$patch"
  echo "New version will be: $new_version"
  
  if ! confirm_tag "Create and tag git repository with new version: ${new_version}?"; then
    echo -e "\nNo version change. Thank you!"
    exit 0
  fi
fi

echo "Checking out main branch..."
git checkout main || { echo "Failed to checkout main branch"; exit 1; }
echo "Fetching updates..."
git fetch --all || { echo "Failed to fetch updates"; exit 1; }
echo "Resetting to origin/main..."
git reset --hard origin/main || { echo "Failed to reset to origin/main"; exit 1; }

# Create changelog PR
branch="update-changelog-$new_version"
git checkout -b "$branch" >/dev/null 2>&1

insert_changelog_version "$new_version"

git add CHANGELOG.md
git commit -m "Update CHANGELOG for $new_version [skip ci]"
git push -u origin "$branch" --quiet

gh pr create \
  --title "Update changelog for $new_version" \
  --body "Automated changelog update before tagging $new_version." \
  --head "$branch" \
  --base main

echo "Please merge the above PR after approval."

repository=$(basename "$(git rev-parse --show-toplevel)" || echo "unknown-repo")

cat << EOF

Tagging Git repository ${repository} with version: $new_version
EOF

git co main
git tag "$new_version" || { echo "Failed to create tag"; exit 1; }
git push origin main "$new_version"

cat << EOF

Jenkins URL: https://ci.braintree.tools/blue/organizations/jenkins/PayPal-Braintree%2F${repository}/detail/${new_version}/1/pipeline

You can inspect the diff between ${current_version} and ${new_version} here: https://github.com/PayPal-Braintree/${repository}/compare/${current_version}...${new_version}

EOF
