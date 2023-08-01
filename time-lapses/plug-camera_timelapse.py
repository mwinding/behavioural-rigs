#!/usr/bin/python3
import time
from picamera2 import Picamera2
​
picam2 = Picamera2()
picam2.configure("still")
picam2.start()
​
experiment_name ='exp_test_zero_long-cable'
N = 96 # Total number of images acquired
​
start_time = time.time()
for i in range(1, N+1):
    r = picam2.capture_request()
    r.save("main", f"{experiment_name}_image{str(i).zfill(5)}.jpg")
    r.release()
    print(f"Captured image {i} of {N} at {time.time() - start_time:.2f}s")
    time.sleep(600)
​
picam2.stop()