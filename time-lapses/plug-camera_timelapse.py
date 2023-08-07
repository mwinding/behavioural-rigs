#!/usr/bin/python3
import time
from picamera2 import Picamera2
import os
import numpy as np

picam2 = Picamera2()
picam2.configure("still")
picam2.start()
success = picam2.autofocus_cycle() # run an auto-focus cycle

experiment_name ='exp' # will create a folder with this name

focus_before_capture = True # do you autofocus before each capture, probably won't work for <3s intervals
duration = 180 # total time of timelapse, in seconds
interval = 60 # time between acquisitions, in seconds
num_captures = int(duration / interval) + 1

# Create the output directory if it doesn't exist
os.makedirs(experiment_name, exist_ok=True)

# Record the initial time for reference
start_time = time.time()

capture_times = []
for i in range(num_captures):

    if(focus_before_capture==True):
        success = picam2.auto_focus() # auto-focus before each interval/capture

    # acquire image
    r = picam2.capture_request()
    r.save("main", f"{experiment_name}/{experiment_name}_image{str(i).zfill(5)}.jpg")

    # Calculate the elapsed time from the start of the time-lapse
    elapsed_time = time.time() - start_time
    capture_times.append(elapsed_time)
    print(f"Captured image {i} of {num_captures} at {elapsed_time:.2f}s")

    r.release()

    # Calculate the expected time for the next capture
    expected_next_capture_time = (i + 1) * interval

    # Calculate the time to sleep for the next capture
    sleep_duration = max(0, expected_next_capture_time - elapsed_time) # if value is negative, 0 will be selected as the max value and passed to time.sleep()
    
    time.sleep(sleep_duration)

picam2.stop()

# save capture_times in case needed in the future, in seconds
np.savetxt(f'{experiment_name}/{experiment_name}_capture-times.csv', capture_times, delimiter=",")