#!/bin/bash

set -e

# Script to generate Falcon-patched container definition files
# Usage: ./generate_falcon_patched_files.sh <environment>

ENVIRONMENT=${1:-dev}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TFVARS_FILE="${SCRIPT_DIR}/../../infrastructure/tfvars/${ENVIRONMENT}.tfvars"
TEMPLATE_FILE="${SCRIPT_DIR}/../../infrastructure/task-definitions/container-definitions/deployer.json.tfpl"
FALCON_PATCH_SCRIPT="${SCRIPT_DIR}/falcon_sensor_task_patch.sh"
CONTAINER_DEFS_DIR="${SCRIPT_DIR}/../../infrastructure/task-definitions/container-definitions"
FRAMEWORK_DEFS_CONTAINER_DIR="${SCRIPT_DIR}/../../infrastructure/framework-task-definitions/container-definitions"
FRAMEWORK_TEMPLATE="${FRAMEWORK_DEFS_CONTAINER_DIR}/deployer_framework.json.tfpl"

echo "🚀 Generating Falcon-patched container definitions for environment: $ENVIRONMENT" 

# Check if tfvars file exists
if [[ ! -f "$TFVARS_FILE" ]]; then
    echo "❌ Error: tfvars file not found: $TFVARS_FILE"
    exit 1
fi

# Check if template file exists
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "❌ Error: Template file not found: $TEMPLATE_FILE"
    exit 1
fi

# Check if falcon patch script exists
if [[ ! -f "$FALCON_PATCH_SCRIPT" ]]; then
    echo "❌ Error: Falcon patch script not found: $FALCON_PATCH_SCRIPT"
    exit 1
fi

# First, handle the framework template (only one file needed)
if [[ -f "$FRAMEWORK_TEMPLATE" ]]; then
    echo "🔧 Processing framework template"
    
    # Generate the output filename
    output_file="${FRAMEWORK_DEFS_CONTAINER_DIR}/deployer_framework_falcon_patched.json.tfpl" 
    
    # Run the Falcon sensor patch script
    echo "🛡️ Running Falcon sensor patch for framework template..."
    FALCON_CID="$FALCON_CID" "$FALCON_PATCH_SCRIPT" "$FRAMEWORK_TEMPLATE" "$output_file"
    
    if [[ -f "$output_file" ]]; then
        echo "✅ Generated: $output_file"
    else
        echo "❌ Failed to generate: $output_file"
        exit 1
    fi
else
    echo "⚠️ Framework template not found: $FRAMEWORK_TEMPLATE"
fi

# Extract deployer_version from tfvars - simple and reliable approach
echo "📋 Extracting deployer versions from $TFVARS_FILE"

# Extract lines between deployer_version = { and }, then clean them up
deployer_versions=$(sed -n '/^[[:space:]]*deployer_version[[:space:]]*=/,/^[[:space:]]*}/p' "$TFVARS_FILE" | \
                    sed '1d;$d' | \
                    grep -E '^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=' | \
                    sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]]*=[[:space:]]*/=/; s/"//g')

if [[ -z "$deployer_versions" ]]; then
    echo "❌ Error: Could not extract deployer_version from tfvars file"
    exit 1
fi

echo "Found deployer versions:"
echo "$deployer_versions"

# Process each deployer
while IFS='=' read -r deployer_name deployer_version; do
    # Clean up whitespace
    deployer_name=$(echo "$deployer_name" | xargs)
    deployer_version=$(echo "$deployer_version" | xargs)
    
    if [[ -z "$deployer_name" || -z "$deployer_version" ]]; then
        continue
    fi
    
    echo "🔧 Processing: $deployer_name (version: $deployer_version)"
    
    # Determine the correct image name based on deployer type
    # Every key maps to key_deployer, except base maps to provision_base_deployer
    if [[ "$deployer_name" == "base" ]]; then
        image_name="provision_base_deployer"
    else
        image_name="${deployer_name}_deployer"
    fi
    
    # Generate the container definition file from template
    temp_container_def=$(mktemp)
    sed -e "s/\${deployer_name}/$image_name/g" \
        -e "s/\${deployer_version}/$deployer_version/g" \
        "$TEMPLATE_FILE" > "$temp_container_def"
    
    echo "📝 Generated temporary container definition for $deployer_name"
    
    # Generate the output filename
    output_file="${CONTAINER_DEFS_DIR}/${deployer_name}_deployer_falcon_patched.json.tfpl"
    
    # Run the Falcon sensor patch script (only takes 2 parameters: input and output)
    echo "🛡️  Running Falcon sensor patch for $deployer_name..."
    FALCON_CID="$FALCON_CID" "$FALCON_PATCH_SCRIPT" "$temp_container_def" "$output_file"
    
    if [[ -f "$output_file" ]]; then
        echo "✅ Generated: $output_file"
    else
        echo "❌ Failed to generate: $output_file"
        rm -f "$temp_container_def"
        exit 1
    fi
    
    # Clean up temporary file
    rm -f "$temp_container_def"
    
done <<< "$deployer_versions"

echo "🎉 Successfully generated all Falcon-patched container definitions!"
