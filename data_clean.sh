#!/bin/bash

# The path to the main directory to clean up, replace '/path/to/data' with your actual path
main_directory='data'

# Iterate over each directory within the main directory
find "$main_directory" -type d -mindepth 1 -maxdepth 1 | while read dir; do
    # Check if directory name contains "UNCERTAINTY"
    if [[ "$dir" == *"UNCERTAINTY"* ]]; then
        # Iterate over all subdirectories of the current directory
        find "$dir" -type d -mindepth 1 -maxdepth 1 | while read subdir; do
            # Check if the subdirectory contains a directory named "pyt_save"
            if [ -d "$subdir/pyt_save" ]; then
                # If yes, pass (do nothing)
                echo "Keeping $subdir as it contains pyt_save."
            else
                # If no, delete the subdirectory
                echo "Deleting $subdir..."
                rm -rf "$subdir"
            fi
        done
    fi
done
