#!/bin/bash

# Path to the main 'data' directory
main_directory='data'

# Find and iterate over all subdirectories within the main directory
find "$main_directory" -type d -mindepth 1 | while read subdir; do
    # Check if the directory is empty
    if [ -z "$(ls -A "$subdir")" ]; then
        # If the directory is empty, echo the directory path (safety check)
        echo "Deleting empty directory: $subdir"
        # Uncomment the following line after confirming it's safe to delete the empty directories
        # rm -rf "$subdir"
    else
        echo "Keeping $subdir - Not empty"
    fi
done
