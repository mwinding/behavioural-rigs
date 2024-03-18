# %%
import pandas as pd
import numpy as np
import json
import subprocess
import pandas as pd
from datetime import datetime
import os
import argparse
import time
import tempfile

################
# functions for pipeline
################

def list_directory_contents(folder_path):
    # Check if the given path is a directory
    if not os.path.isdir(folder_path):
        print(f"{folder_path} is not a valid directory path.")
        return
    
    # Get the list of items in the directory
    contents = os.listdir(folder_path)
    
    return contents

# shell script content
def sbatch_rsync(remove_files, username, ip_address, save_path):
    shell_script_content = f"""#!/bin/bash
    #SBATCH --job-name=rsync_pi
    #SBATCH --ntasks=1
    #SBATCH --time=08:00:00
    #SBATCH --mem=64G
    #SBATCH --partition=cpu
    #SBATCH --cpus-per-task=8
    #SBATCH --output=slurm-%j.out
    #SBATCH --mail-user=$(whoami)@crick.ac.uk
    #SBATCH --mail-type=FAIL

    rsync -avzh --progress {remove_files}{username}@${ip_address}:/home/{username}/data/ {save_path}/raw_data
    rsync_status=$?

    # check rsync status and output file if it fails to allow user to easily notice
    if [ $rsync_status -ne 0 ]; then
        # If rsync fails, create a file indicating failure
        echo "Rsync failed for IP: $ip_var" > "FAILED-rsync_IP-{ip_address}.out"
    fi

    ssh {username}@{ip_address} "find data/ -mindepth 1 -type d -empty -delete"
    """

    # Create a temporary file to hold the SBATCH script
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_script:
        tmp_script.write(shell_script_content)
        tmp_script_path = tmp_script.name

    # Submit the SBATCH script
    process = subprocess.run(["sbatch", tmp_script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Delete the temporary file after submission
    os.unlink(tmp_script_path)

    # Check the result and extract job ID from the output
    if process.returncode == 0:
        job_id_output = process.stdout.strip()
        print(job_id_output)

        job_id = job_id_output.split()[-1]

        print(process.stdout)
    else:
        print("Failed to submit job")
        print(process.stderr)
        exit(1)

# extract frames from video and crop centre 150 pixels
def extract_frames(video_path, interval=1, save_path='', crop=[525, 675], stop_frame = 250): #250
    """
    Extract frames from a video.
    
    :param video_path: Path to the video file.
    :param interval: Interval of frames to extract (1 = every frame, 2 = every other frame, etc.)
    """

    vidcap = cv2.VideoCapture(video_path)
    success, image = vidcap.read()
    count = 0
    frames = []

    while success:
        if count <= stop_frame and (count % interval == 0):  # Save frame every 'interval' frames
            frames.append(image)
        success, image = vidcap.read()
        count += 1

    vidcap.release()
 
    os.makedirs(f'{save_path}/sequence/', exist_ok=True)
    for i, frame in enumerate(frames):
        frame = frame[:, crop[0]:crop[1]]
        cv2.imwrite(f'{save_path}/sequence/{str(i).zfill(3)}.jpg', frame)

    return(frames)

def stitch_images(frames, save_path, tile_config, name):
    path = f'{save_path}/pupae_data/raw_data/sequence'
    if(tile_config==True):
        source_path = f'{save_path}/TileConfiguration.txt'
        destination_path = f'{path}/TileConfiguration.txt'
        shutil.copy2(source_path, destination_path)

    print(f'frame count {len(frames)}')

    plugin = "Grid/Collection stitching"
    args = {
        "type": "[Grid: row-by-row]",
        "order": "[Right & Down]",
        "grid_size_x": f"{(len(frames))}",
        "grid_size_y": "1",
        "tile_overlap": "86",
        "first_file_index_i": "0",
        "directory": f'{path}',
        "file_names": "{iii}.jpg",
        "output_textfile_name": "TileConfiguration.txt",
        "fusion_method": "[Linear Blending]",
        "regression_threshold": "0.30",
        "max/avg_displacement_threshold": "2.50",
        "absolute_displacement_threshold": "3.50",
        "compute_overlap": True,
        "computation_parameters": "[Save computation time (but use more RAM)]",
        "image_output": "[Write to disk]",
        "output_directory": f'{path}'
    }

    # if tile_config=True, stitch based on tile configuration file
    if(tile_config==True):

        args = {
            "type": "[Positions from file]",
            "order": "[Defined by TileConfiguration]",
            "layout_file": f"TileConfiguration.txt",
            "directory": f'{path}',
            "fusion_method": "[Linear Blending]",
            "regression_threshold": "0.30",
            "max/avg_displacement_threshold": "2.50",
            "absolute_displacement_threshold": "3.50",
            "compute_overlap": True,
            "computation_parameters": "[Save computation time (but use more RAM)]",
            "image_output": "[Write to disk]",
            "output_directory": f'{path}'
        }

    # run plugin
    ij.py.run_plugin(plugin, args)

    # Fiji stitcher saves output as separate 8-bit R, G, and B images
    # merge them together and save here

    # Open the 8-bit grayscale TIFF images
    image_r = Image.open(f'{path}/img_t1_z1_c1')
    image_g = Image.open(f'{path}/img_t1_z1_c2')
    image_b = Image.open(f'{path}/img_t1_z1_c3')

    # Merge the images into one RGB image
    image_rgb = Image.merge('RGB', (image_r, image_g, image_b))

    # Define crop box with left, upper, right, and lower coordinates; heuristically defined by looking at uncropped images
    crop_box = (0, 0, 1045, image_rgb.height)  # Right coordinate is 1050, lower coordinate is the height of the image

    # Crop the image
    cropped_image_rgb = image_rgb.crop(crop_box)

    # save the image
    cropped_image_rgb.save(f'{save_path}/pupae_data/unwrapped/{name}.jpg')
    
    # delete everything from sequence directory and then directory itself
    try:
        shutil.rmtree(f'{path}/')
    except:
        print('Cannot delete folder!')

    return(f'{save_path}/pupae_data/unwrapped/{name}.jpg')
    
def is_job_array_completed(job_id):
    cmd = ["sacct", "-j", f"{job_id}", "--format=JobID,State", "--noheader"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    lines = result.stdout.strip().split('\n')

    # Initialize flags
    all_completed = True

    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue  # Skip any malformed lines

        # Extract and ignore array job steps (e.g., "12345678_1") for simplicity
        job_id_part, job_state = parts[0], parts[1]
        if "_" in job_id_part and not job_id_part.endswith("batch"):  # Focus on array tasks excluding batch job steps
            if job_state not in ["COMPLETED", "FAILED", "CANCELLED"]:
                all_completed = False
                break

    return all_completed

#####################
#################
# PIPELINE STARTS
#################

# default argument values
username = 'rotator'
ip_address = '192.168.1.100'
remove_files = True

# pulling user-input variables from command line
parser = argparse.ArgumentParser(description='Pupae video pipeline: take IP address of RPi taking pupae videos, syncs to NEMO, processes videos, and determines number of pupae per vial')
parser.add_argument('-ip', '--ip-address', type=str, required=True, default=ip_address, help='IP addres of RPi to sync from')
parser.add_argument('-e', '--experiment-name', type=str, required=True, help='name of experiment; should match existing experiment')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-r', '--remove-files', type=bool, default=remove_files, help='whether to remove files from RPi source')
parser.add_arguemnt('-ec', '--experiment-csv', type=str, required=True, help='path to the CSV with experimental details')

# ingesting user-input arguments
args = parser.parse_args()
ip_address = args.ip_address
username = args.username
experiment_name = args.experiment_name
remove_files = args.remove_files
experiment_csv_path = args.experiment_csv

# save-path on NEMO, must exist already in this case
save_path = f'/camp/lab/windingm/data/instruments/behavioural_rigs/plugcamera/{experiment_name}/pupae'

# load information about the expeirment
exp_csv = pd.read_csv(experiment_csv_path)
#### DO SOMETHING WITH THIS INFORMATION ####

# Check if a save folder exists already and create it if not
if not os.path.exists(save_path.replace('/pupae', '')):
    print(f'The parent folder of: {save_path} does not exist! Check if the experiment was transferred successfully from plugcamera pipeline_1')

# create subfolders
if not os.path.exists(save_path):
    os.makedirs(save_path, exist_ok=True)

if not os.path.exists(f'{save_path}/raw_data'):
    os.makedirs(f'{save_path}/raw_data', exist_ok=True)

if not os.path.exists(f'{save_path}/predictions'):
    os.makedirs(f'{save_path}/predictions', exist_ok=True)

#########################
#### TRANSFER DATA ######
# transfer raw data from RPis to NEMO

start_transfer = datetime.now()

# remove source files from RPi or not, is a user-input parameter
if(remove_files==True):
    remove_files = '--remove-source-files ' # need the space for command line syntax
if(remove_files==False):
    remove_files = ''

sbatch_rsync(remove_files, username, ip_address, save_path)

# Function to check if the array job is completed
seconds = 60
print(f"Wait for {seconds} seconds before checking if slurm job has completed")
time.sleep(seconds)

# Wait for the array job to complete
print(f"Waiting for slurm job {job_id} to complete...")
while not is_job_array_completed(job_id):
    print(f"Slurm job {job_id} is still running. Waiting...")
    time.sleep(30)  # Check every 30 seconds

print(f"Slurm job {job_id} has completed.\n")
end_transfer = datetime.now()

########
# Unwrap videos
########

start_processing = datetime.now()
fiji_path = '/camp/home/shared/Fiji-installation/Fiji.app'
tile_config = True

# Start ImageJ
scyjava.config.add_option('-Xmx6g')
ij = imagej.init(fiji_path) # point to local installation

video_path = f'{save_path}/raw_data'

# batch process videos in folder
paths = []
names = []
if(os.path.isdir(video_path)):
    video_files = [f'{video_path}/{f}' for f in os.listdir(video_path) if os.path.isfile(os.path.join(video_path, f)) and not (f.endswith('.txt') or f=='.DS_Store')]
    for video_file_path in video_files:
        frames = extract_frames(video_file_path, interval=5, save_path=video_path)
        name = os.path.basename(video_file_path)
        path = stitch_images(frames=frames, save_path=video_path, tile_config=tile_config, name=name)

        names.append(name) # return file name for subsequent saving
        paths.append(path) # return all paths of unwrapped videos for subsequent processing

############
# SLEAP predictions

centroid_path = '/camp/lab/windingm/home/shared/SLEAP_models/pupae_detection/240306_235934.centroid'
centered_instance_path = '/camp/lab/windingm/home/shared/SLEAP_models/pupae_detection/240306_235934.centered_instance'

paths_string = ' '.join(paths)
names_string = ' '.join(names)

shell_script_content = f"""#!/bin/bash

# usage: to run on pupae videos after unwrapping:
# sbatch --export=EXP_NAME=test_exp,RIG_NUMBERS="50 51 52",REMOVE=False sbatch-transfer.sh

#SBATCH --job-name=SLEAP_training
#SBATCH --ntasks=1
#SBATCH --time=08:00:00
#SBATCH --mem=64G
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=4
#SBATCH --array=1-{len(paths)}
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate sleap
IFS=' ' read -r -a paths_array <<< "{paths_string}"
IFS=' ' read -r -a paths_array <<< "{names_string}"

path_var="${{paths_array[$SLURM_ARRAY_TASK_ID-1]}}"
name_var="${{names_array[$SLURM_ARRAY_TASK_ID-1]}}"

sleap-track $path_var -m {centroid_path} -m {centered_instance_path} -o {save_path}/predictions/$name_var.predictions.slp
sleap-convert $path_var.predictions.slp -o $path_var.json --format json"""

# Create a temporary file to hold the SBATCH script
with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_script:
    tmp_script.write(shell_script_content)
    tmp_script_path = tmp_script.name

# Submit the SBATCH script
process = subprocess.run(["sbatch", tmp_script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Delete the temporary file after submission
os.unlink(tmp_script_path)

# Check the result and extract job ID from the output
if process.returncode == 0:
    job_id_output = process.stdout.strip()
    print(job_id_output)

    job_id = job_id_output.split()[-1]

    print(process.stdout)
else:
    print("Failed to submit job")
    print(process.stderr)
    exit(1)

# Function to check if the array job is completed
seconds = 60
print(f"Wait for {seconds} seconds before checking if slurm job has completed")
time.sleep(seconds)

# Wait for the array job to complete
print(f"Waiting for array job {job_id} to complete...")
while not is_job_array_completed(job_id):
    print(f"Array job {job_id} is still running. Waiting...")
    time.sleep(30)  # Check every 30 seconds

print(f"Array job {job_id} has completed.\n")
print(f"SLEAP predictions complete!\n")

############
# pull out number of pupae and add to CSV

prediction_path = f'{save_path}/predictions'

counts = []
if(os.path.isdir(prediction_path)):
    video_files = [f'{prediction_path}/{f}' for f in os.listdir(prediction_path) if os.path.isfile(os.path.join(prediction_path, f)) and not (f.endswith('.jpg') or f=='.DS_Store')]
    for video_file in video_files:
        with open(video_file, 'r') as file:
            data = json.load(file)

            pupae_count = len(data['labels'][0]['_instances'])
            print([pupae_count, video_file])
            counts.append([pupae_count, video_file])

df = pd.DataFrame(counts, columns = ['pupae_count', 'dataset'])
df.to_csv(f'{prediction_path}/pupae_counts.csv')

# body_x, body_y = data['labels'][0]['_instances'][0]['_points']['0']['x'], data['labels'][0]['_instances'][0]['_points']['0']['y']
# tail_x, tail_y = data['labels'][0]['_instances'][0]['_points']['1']['x'], data['labels'][0]['_instances'][0]['_points']['1']['y']
# head_x, head_y = data['labels'][0]['_instances'][0]['_points']['2']['x'], data['labels'][0]['_instances'][0]['_points']['2']['y']

end_processing = datetime.now()

################################
### HOW LONG DID IT TAKE? ######

# calculate script time
rsync_time = end_transfer - start_transfer
processing_time = end_processing - start_processing
total_time = end_processing - start_transfer

# Convert duration to total seconds for formatting
rsync_seconds = int(rsync_time.total_seconds())
processing_seconds = int(processing_time.total_seconds())
total_seconds = int(total_time.total_seconds())

# Format durations as MM:SS
rsync_time_formatted = f'{rsync_seconds // 60}:{rsync_seconds % 60:02d}'
processing_time_formatted = f'{processing_seconds // 60}:{processing_seconds % 60:02d}'
total_time_formatted = f'{total_seconds // 60}:{total_seconds % 60:02d}'


print('\n\n\n')
print(f'Rsync time: {rsync_time_formatted}')
print(f'Processing time: {processing_time_formatted}')
print(f'\nTotal time: {total_time_formatted}')