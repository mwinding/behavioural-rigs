import time
from time import sleep
from time import strftime
import RPi.GPIO as GPIO
from picamera2 import Picamera2, Preview
from libcamera import controls
from datetime import datetime
import socket

experiment_duration = 10
framerate = 30
resolution = (1200, 1200)
exposure = 5000
lensPosition = 8.0
rig_name = socket.getfqdn()

#exp='Test'
#lighting = 'white'
#lighting_paradigm = 'ON'
#experiment_name = parent_directory + '/' + date + '_' + lighting + '_' + lighting_paradigm + '_'+ exp
#experiment_name = parent_directory 

# Pin definitions
shutdown_pin = 2
record_pin = 27
stop_pin = 22
red_led = 23
yellow_led = 24

# Suppress warnings
GPIO.setwarnings(False)

# Use "GPIO" pin numbering
GPIO.setmode(GPIO.BCM)

# Set up GPIO input pins with internal pull-up resistors (Push buttons)
GPIO.setup(shutdown_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(record_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(stop_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Set up GPIO output pins (LED's)
GPIO.setup(red_led, GPIO.OUT)
GPIO.setup(yellow_led, GPIO.OUT)

# Start with both LED's off
GPIO.output(red_led,GPIO.LOW)
GPIO.output(yellow_led,GPIO.LOW)

picam2 = Picamera2()
camera_config = picam2.create_preview_configuration({'size': resolution})
picam2.configure(camera_config)
picam2.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": lensPosition, "FrameRate": framerate, "ExposureTime": exposure})

# modular function to shutdown Pi
def shut_down():
    print("shutting down")
    command = "/usr/bin/sudo /sbin/shutdown -h now"
    import subprocess
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
    output = process.communicate()[0]
    print(output)


try:
    video_counter = 1

    while True:
        #short delay, otherwise this code will take up a lot of the Pi's processing power
        time.sleep(0.2)

        if GPIO.input(record_pin)==False:
            GPIO.output(red_led,GPIO.HIGH) # Red LED ON to indicate the device is recording
            
            #Labels the recording year-month-day_hour-minute-second
            date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            print("acquiring...")
            picam2.start_and_record_video(show_preview=True, output=f"data/{date}_pupae_video-{video_counter}.mp4", duration = experiment_duration)
            picam2.stop_preview()

            GPIO.output(red_led,GPIO.LOW) # Red LED OFF to indicate the recording stopped
            
            video_counter += 1

        # Check button if we want to shutdown the Pi safely
        if GPIO.input(shutdown_pin)==False:
            # Debounce the button, makes sure you don't accidentally shut down the device with a short press
            time.sleep(0.2) 
            if GPIO.input(stop_pin) == False:
                shut_down()
                
finally:
    GPIO.cleanup()  # Ensure GPIO resources are freed and pins are reset upon exit