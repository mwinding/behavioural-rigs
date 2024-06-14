
import subprocess
import pandas as pd
from datetime import datetime
import os
import argparse
import time
import tempfile

# default argument values
username = 'plugcamera'
ip_path = 'ip_addresses.csv'
remove_files = False

# pulling user-input variables from command line
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-ip', '--ip_path', type=str, required=True, default=ip_path, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-e', '--experiment-name', type=str, required=True, help='name of experiment, will create a folder')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, default=[], help='list of rig names')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-r', '--remove-files', action='store_true', help='whether to remove files from RPi source')

# ingesting user-input arguments
args = parser.parse_args()
ip_path = args.ip_path
list_names = args.list_of_rig_names
username = args.username
experiment_name = args.experiment_name
remove_files = args.remove_files

# save-path on NEMO
save_path = f'/camp/lab/windingm/data/instruments/behavioural_rigs/plugcamera/{experiment_name}'

# pull IP address data
data = pd.read_csv(ip_path)
IPs = data.IP_address
rig_num = data.rig_number

# only pulls IPs of interest and runs the script on those
# this is ignored if no list_names is input with `-l` argument; instead all pis are run
if(len(list_names)>0):
    data.index = data.rig_number
    IPs = data.loc[list_names, 'IP_address'].values
    rig_num = list_names

# Check if a save folder exists already and create it if not
# create subfolders
if not os.path.exists(save_path):
    os.makedirs(save_path, exist_ok=True)

if not os.path.exists(f'{save_path}/raw_data'):
    os.makedirs(f'{save_path}/raw_data', exist_ok=True)

if not os.path.exists(f'{save_path}/mp4s'):
    os.makedirs(f'{save_path}/mp4s', exist_ok=True)

#########################
#### TRANSFER DATA ######
# transfer raw data from RPis to NEMO

start_transfer = datetime.now()

len(IPs)
IPs_string = ' '.join(IPs)
rig_num_str = [f'pc{x}' for x in rig_num]
rigs_string = ' '.join(rig_num_str)

# remove source files from RPi or not, is a user-input parameter
if remove_files==True: remove_files_option = '--remove-source-files '  
if remove_files==False: remove_files_option = '' 

print('\nremove_files variable:')
print(remove_files_option)
print('\n')

# shell script content
shell_script_content = f"""#!/bin/bash
#SBATCH --job-name=rsync_pis
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --array=1-{len(IPs)}
#SBATCH --partition=ncpu
#SBATCH --mem=10G
#SBATCH --time=08:00:00

# convert ip_string to shell array
IFS=' ' read -r -a ip_array <<< "{IPs_string}"
ip="${{ip_array[$SLURM_ARRAY_TASK_ID-1]}}"

IFS=' ' read -r -a rig_array <<< "{rigs_string}"
rig="${{rig_array[$SLURM_ARRAY_TASK_ID-1]}}"

# rsync using the IP address obtained above

echo $ip

rsync -avzh --progress plugcamera@$ip:/home/plugcamera/data/ {save_path}/raw_data
rsync -avzh --progress {remove_files_option}plugcamera@$ip:/home/plugcamera/data/ {save_path}/raw_data
rsync_status=$?

# check rsync status and output file if it fails to allow user to easily notice
if [ $rsync_status -ne 0 ]; then
    # If rsync fails, create a file indicating failure
    echo "Rsync failed for IP: $ip" > "FAILED-rsync_{experiment_name}_${{rig}}_IP-${{ip}}.out"
fi

ssh plugcamera@$ip "find data/ -mindepth 1 -type d -empty -delete"
"""

# Create a temporary file to hold the SBATCH script
with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_script:
    tmp_script.write(shell_script_content)
    tmp_script_path = tmp_script.name

# Submit the SBATCH script
process = subprocess.run(["sbatch", tmp_script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Optionally, delete the temporary file after submission
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

seconds = 60
print(f"Wait for {seconds} seconds before checking if array job has completed")
time.sleep(seconds)

# Wait for the array job to complete
print(f"Waiting for array job {job_id} to complete...")
while not is_job_array_completed(job_id):
    print(f"Array job {job_id} is still running. Waiting...")
    time.sleep(30)  # Check every 30 seconds

print(f"Array job {job_id} has completed.\n")
end_transfer = datetime.now()

###############################
###### PROCESS DATA ###########
# convert to .mp4 and crop
# adapted from Lucy Kimbley

start_processing = datetime.now()

def list_directory_contents(folder_path):
    # Check if the given path is a directory
    if not os.path.isdir(folder_path):
        print(f"{folder_path} is not a valid directory path.")
        return
    
    # Get the list of items in the directory
    contents = os.listdir(folder_path)
    
    return contents

# generate and crop mp4 videos for each directory
def run_commands_in_directory(directory_path, save_path):
    # Define the commands
    generate_mp4 = f"ffmpeg -framerate 7 -pattern_type glob -i '{directory_path}/*.jpg' -c:v libx264 -pix_fmt yuv420p {directory_path}_raw.mp4"
    crop_mp4 = f"ffmpeg -i {directory_path}_raw.mp4 -filter:v 'crop=1750:1750:1430:360' {save_path}.mp4"
    remove_uncropped = f"rm {directory_path}_raw.mp4"

    # Run the commands using subprocess
    subprocess.run(generate_mp4, shell=True)
    subprocess.run(crop_mp4, shell=True)
    subprocess.run(remove_uncropped, shell=True)

# Path to the parent directory with the folders you want to list
base_path = f'{save_path}/raw_data'
directory_contents = list_directory_contents(base_path)

if directory_contents:
    print(f"Contents of {base_path}:")
    for item in directory_contents:
        print(item)
else:
    print("No contents found.")

if directory_contents:
    print(f"Processing each directory in {base_path}:")
    for directory in directory_contents:
        print(f"\nProcessing: {base_path}/{directory}")
        run_commands_in_directory(f'{save_path}/raw_data/{directory}', f'{save_path}/mp4s/{directory}')
else:
    print("No directories found.")

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
