#!/bin/bash

# this script clones a microSD card image (raspberry_pi_os.img) of a Raspberry Pi to all USB connected microSD cards
# run using `sudo ./clone.sh`

# Path to the Raspberry Pi OS image
IMAGE_PATH="raspberry_pi_os.img"

# Detect all removable storage devices
echo "Detecting removable devices..."
TARGETS=$(lsblk -ln -o NAME,RM,TYPE | awk '$2 == "1" && $3 == "disk" {print "/dev/" $1}')

# Exit if no target devices are found
if [ -z "$TARGETS" ]; then
    echo "No removable devices found. Exiting."
    exit 1
fi

echo "Detected target devices:"
echo "$TARGETS"

# Unmount all partitions on target devices before writing
for device in $TARGETS; do
    echo "Unmounting partitions on $device..."
    sudo umount ${device}* 2>/dev/null
done

# Write the image to each detected device
for device in $TARGETS; do
    if [ -e "$device" ]; then  # Check if the device still exists
        echo "Writing image to $device..."
        sudo dd if="$IMAGE_PATH" of="$device" bs=4M conv=fsync status=progress || echo "Failed to write to $device. Skipping..."
    else
        echo "Device $device no longer available. Skipping..."
    fi
done

echo "Batch writing completed!"