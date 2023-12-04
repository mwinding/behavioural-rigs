import picamera
import time
import datetime as dt

parent_directory = '/home/pi/Desktop/Test/2023-09-27'
date='2023_09-27'
exp='large-slide_rigV2_07mm_08agarose_needle-top_limited-FOV_29Larvae_framerate1_4hr_video4'
lighting = 'white'
lighting_paradigm = 'ON'
experiment_name = parent_directory + '/' + date + '_' + lighting + '_' + lighting_paradigm + '_'+ exp

experiment_duration = 14400

with picamera.PiCamera() as camera:
        camera.resolution = (1200, 1200)
        #camera.color_effects=(128,128) #Black and white
        camera.framerate = 1
        camera.rotation = 90
        #camera.annotate_background = picamera.Color('black')
        camera.start_preview(alpha=255)
        input('Press ENTER to start recording')
        start = dt.datetime.now()
        camera.start_recording(experiment_name + ".h264")
        while not (dt.datetime.now() - start).total_seconds() > experiment_duration:
            camera.annotate_text = str((dt.datetime.now()-start).total_seconds())
        camera.stop_recording()