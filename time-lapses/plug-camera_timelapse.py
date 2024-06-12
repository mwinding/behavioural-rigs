#!/usr/bin/python3
import time
from datetime import datetime
from picamera2 import Picamera2
import os
import numpy as np
import argparse
import subprocess

# Example usage
# python plug-camera_timelapse.py -r [rig_name]
# 
# optional arguments:   -t [timeout for SSH connections in seconds, default: 10]
#                       -u [username for SSH connections, default: 'plugcamera']

duration = 518400 # total time of timelapse, in seconds
interval = 600 # time between acquisitions, in seconds
experiment_name ='exp' # will create a folder with this name
focus_in_loop = False # do you autofocus before each capture, probably won't work for <3s intervals
current_time = ''

# pulling user-input variables from command line
parser = argparse.ArgumentParser(description='Timelapse script for plug cameras')
parser.add_argument('-d', '--duration', dest='duration', action='store', type=int, required=True, default=duration, help='acquisition duration in seconds')
parser.add_argument('-i', '--interval', dest='interval', action='store', type=int, required=True, default=interval, help='acquisition interval between frames in seconds')
parser.add_argument('-e', '--experiment_name', dest='experiment_name', action='store', type=str, required=True, default=duration, help='name of experiment, will create a folder')
parser.add_argument('-r', '--rig_name', dest='rig_name', action='store', type=str, required=True, help='name of rig')
parser.add_argument('-f', '--focus-in-loop', dest='focus_in_loop', action='store', type=bool, default=focus_in_loop, help='whether to run an autofocus cycle for each frame acquisition')
parser.add_argument('-t', '--time', dest='current_time', action='store', type=str,  default=current_time, help='the current time, for using the batch script') 

# ingesting user-input arguments
args = parser.parse_args()
duration = args.duration
interval = args.interval
experiment_name = args.experiment_name
focus_in_loop = args.focus_in_loop
rig_name = args.rig_name
current_time = args.current_time

picam2 = Picamera2()
picam2.configure("still")
picam2.start()
success = picam2.autofocus_cycle() # run an auto-focus cycle

num_captures = int(duration / interval) + 1

# record date/time for naming purposes
now = datetime.now()
now = now.strftime("%Y-%m-%d_%H-%M-%S")

# check if the current time was input as parameter in batch script; ignore if using without batch script
if(current_time!=''):
    now = current_time

# Create the output directory if it doesn't exist
os.makedirs('data', exist_ok=True)
os.makedirs(f'data/{now}_{rig_name}_{experiment_name}', exist_ok=True)

# Record the initial time to calculate timelapse intervals
start_time = time.time()

capture_times = []
for i in range(num_captures):

    if(focus_in_loop==True):
        success = picam2.autofocus_cycle() # auto-focus before each interval/capture

    # acquire image
    r = picam2.capture_request()
    r.save("main", f"data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_image{str(i).zfill(5)}.jpg")

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
np.savetxt(f'data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_capture-times.csv', capture_times, delimiter=",")

# restarting RPi
print(f'restarting {rig_name}')
ssh_command = f'sudo shutdown -r now'

try:
    check_result = subprocess.run(ssh_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    feedback = check_result.stdout.decode().strip()
    error_feedback = check_result.stderr.decode().strip()
    
    if feedback:
        print(f'\t{feedback}')
    if error_feedback:
        print(f'\tError: {error_feedback}')
except subprocess.CalledProcessError as e:
    print(f'\tFailed to restart {rig_name}: {e}')