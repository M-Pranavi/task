#!/bin/bash

set -e

# Script to generate Falcon-patched container definition files
# Handles two cases:
# 1. One common framework deployer template
# 2. Multiple task-definition deployer templates based on taskdefinitions.tf

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKDEFS_FILE="${SCRIPT_DIR}/../../infrastructure/csor-orchestration/taskdefinitions.tf"
FALCON_PATCH_SCRIPT="${SCRIPT_DIR}/falcon_sensor_task_patch.sh"
TASK_DEFS_CONTAINER_DIR="${SCRIPT_DIR}/../../infrastructure/task-definitions/container-definitions"
FRAMEWORK_DEFS_CONTAINER_DIR="${SCRIPT_DIR}/../../infrastructure/framework-task-definitions/container-definitions"
FRAMEWORK_TEMPLATE="${FRAMEWORK_DEFS_CONTAINER_DIR}/deployer_framework.json.tfpl"

echo "🚀 Generating Falcon-patched container definitions"

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

# Now handle the task-definitions templates
# Check if taskdefinitions file exists
if [[ ! -f "$TASKDEFS_FILE" ]]; then
    echo "❌ Error: taskdefinitions file not found: $TASKDEFS_FILE"
    exit 1
fi

# Extract deployer information from taskdefinitions.tf (only for task-definitions)
echo "📋 Extracting deployer information for task-definitions from $TASKDEFS_FILE"

# Format: module_name|name
deployer_info=$(grep -A 5 "^module \".*\"" "$TASKDEFS_FILE" | \
                grep -E "^module|source[[:space:]]*=|name[[:space:]]*=" | \
                awk 'BEGIN {mod=""; src=""; name="";} 
                     /^module/ {if (mod != "" && src != "" && name != "") {
                                  if (src == "../task-definitions" && !(name ~ /_framework$/)) {
                                    print mod "|" name;
                                  }
                                }; 
                               mod=$2; gsub(/["\{\}]/,"",mod); src=""; name=""} 
                     /source[[:space:]]*=/ {src=$3; gsub(/["\{\},]/,"",src)} 
                     /name[[:space:]]*=/ {name=$3; gsub(/["\{\},]/,"",name)} 
                     END {if (mod != "" && src != "" && name != "") {
                           if (src == "../task-definitions" && !(name ~ /_framework$/)) {
                             print mod "|" name;
                           }
                         }}')

# Check if we found any task-definition deployers
if [[ -z "$deployer_info" ]]; then
    echo "⚠️ No task-definition deployers found in taskdefinitions.tf"
else
    echo "Found task-definition deployers:"
    echo "$deployer_info"

    # Process each task-definition deployer
    while IFS='|' read -r module_name deployer_name; do
        # Skip if any field is empty
        if [[ -z "$module_name" || -z "$deployer_name" ]]; then
            continue
        fi
        
        echo "🔧 Processing: $module_name (name: $deployer_name)"

        # Use the task-definitions template
        TEMPLATE_FILE="$TASK_DEFS_CONTAINER_DIR/deployer.json.tfpl"
        
        # Check if template file exists
        if [[ ! -f "$TEMPLATE_FILE" ]]; then
            echo "❌ Error: Template file not found: $TEMPLATE_FILE"
            exit 1
        fi

        # Determine the image name for the container definition
        # Add "baseline_" prefix for base_deployer
        if [[ "$deployer_name" == "base_deployer" ]]; then
            image_name="baseline_base_deployer"
        else
            image_name="$deployer_name"
        fi

        # Generate the container definition file from template
        # Replace ${image_name} but preserve ${name} template variable
        temp_container_def=$(mktemp)
        sed -e "s/\${image_name}/$image_name/g" "$TEMPLATE_FILE" > "$temp_container_def"

        echo "📝 Generated temporary container definition for $deployer_name (image: $image_name, preserving \${name})"
        
        # Generate the output filename
        output_file="${TASK_DEFS_CONTAINER_DIR}/${deployer_name}_falcon_patched.json.tfpl"

        # Run the Falcon sensor patch script
        echo "🛡️ Running Falcon sensor patch for $deployer_name..."
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

    done <<< "$deployer_info"
fi

echo "🎉 Successfully generated all Falcon-patched container definitions!"
echo "📋 Summary of approach:"
echo "1. Created a single framework-patched file from the common framework template"
echo "2. Generated individual patched files for each task-definition deployer"
echo "3. Added 'baseline_' prefix to base_deployer image name"
