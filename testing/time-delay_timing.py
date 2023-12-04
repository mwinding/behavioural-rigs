# %%
# testing time using adaptive interval

# Time.sleep() is accurately quite accurate on the scale of seconds
# We have experienced that it is inconsistent in practice though, 
# suggesting there is a delay introduced by camera acquisition. 
# Below I test what happens when we add a 
# randomised camera delay between 150-300ms. 
# I then used an adaptive interval between acquisitions to take 
# into account the measured delay at each frame.

import time
import os
import random
import numpy as np

# normal use of time to add delay interval to timelapse
def time_test(expected_interval, duration, simulated_camera_delay):

    # Calculate the number of captures based on the duration and expected interval
    num_captures = int(duration / expected_interval)

    # Record the start time for reference
    start_time = time.time()

    captures = []
    for i in range(num_captures + 1):

        # simulated camera delay
        time.sleep(simulated_camera_delay)

        # Calculate the elapsed time from the start of the time-lapse
        elapsed_time = time.time() - start_time
        captures.append(elapsed_time)
        print(f"capture at: {elapsed_time:0.5f}")

        time.sleep(expected_interval)

    return(captures)

# adding adaptive time intervals after measuring camera acquisition
def adaptive_time_test(expected_interval, duration, simulated_camera_delay, add_noise=True):

    # Calculate the number of captures based on the duration and expected interval
    num_captures = int(duration / expected_interval)

    # Record the start time for reference
    start_time = time.time()

    captures = []
    for i in range(num_captures + 1):
        # Generate a unique filename for each capture
        #filename = f"{output_directory}/image_{i:04d}.jpg"

        # Capture an image and save it with the generated filename
        #camera.capture(filename)

        # simulated camera delay
        if(add_noise):
            simulated_camera_delay_rand = random.uniform(0.75*simulated_camera_delay, 1.5*simulated_camera_delay)
            time.sleep(simulated_camera_delay_rand)
        if(add_noise==False):
            time.sleep(simulated_camera_delay)

        # Calculate the elapsed time from the start of the time-lapse
        elapsed_time = time.time() - start_time
        captures.append(elapsed_time)
        print(f"capture at: {elapsed_time:0.5f}")

        # Calculate the expected time for the next capture
        expected_next_capture_time = (i + 1) * expected_interval

        # Calculate the time to sleep for the next capture
        sleep_duration = max(0, expected_next_capture_time - elapsed_time)

        # Wait for the adjusted delay before capturing the next image
        time.sleep(sleep_duration)

    return(captures)

# Example usage
expected_interval = 1  # Expected interval between captures (in seconds)
duration = 20  # Capture images for 20 seconds (20 images in this example)
delay = 0.2 # 200ms camera delay for testing

captures_control = time_test(expected_interval, duration, simulated_camera_delay=0)
captures_delay = time_test(expected_interval, duration, simulated_camera_delay=delay)
captures_delay_adaptive = adaptive_time_test(expected_interval, duration, simulated_camera_delay=delay)

print(f'Median interval in control: {np.median(np.diff(captures_control)):0.5f} +/- {np.std(np.diff(captures_control)):0.5f}')
print(f'Median interval with camera delay: {np.median(np.diff(captures_delay)):0.5f} +/- {np.std(np.diff(captures_delay)):0.5f}')
print(f'Median adaptive interval with camera delay: {np.median(np.diff(captures_delay_adaptive)):0.5f} +/- {np.std(np.diff(captures_delay_adaptive)):0.5f}')

# %%
# example timelapse script
# adaptive interval

def capture_time_lapse_with_adjusted_delay(expected_interval, duration, output_directory):
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_directory, exist_ok=True)

        # Initialize the PiCamera
        with picamera.PiCamera() as camera:
            camera.resolution = (1280, 720)  # Set the resolution as per your requirement

            # Calculate the number of captures based on the duration and expected interval
            num_captures = int(duration / expected_interval)

            # Record the initial time for reference
            last_capture_time = time.time()

            captures = []
            for i in range(num_captures):
                # Generate a unique filename for each capture
                filename = f"{output_directory}/image_{i:04d}.jpg"

                # Capture an image and save it with the generated filename
                camera.capture(filename)

                # Calculate the elapsed time from the start of the time-lapse
                elapsed_time = time.time() - start_time
                captures.append(elapsed_time)
                
                # Calculate the expected time for the next capture
                expected_next_capture_time = (i + 1) * expected_interval

                # Calculate the time to sleep for the next capture
                sleep_duration = max(0, expected_next_capture_time - elapsed_time)

                # Wait for the adjusted delay before capturing the next image
                time.sleep(sleep_duration)

        print("Time-lapse capture completed.")
        return(captures)
    except Exception as e:
        print(f"Error: {e}")

# Example usage
expected_interval_seconds = 5  # Expected interval between captures (in seconds)
duration_seconds = 60  # Capture images for 60 seconds (10 images in this example)
output_dir = "time_lapse_output_with_adjustment"

capture_time_lapse_with_adjusted_delay(expected_interval_seconds, duration_seconds, output_dir)
