
import subprocess
import pandas as pd
from datetime import datetime
import os
import argparse
import time
import tempfile

# default argument values
username = 'sideview'
ip_path = 'inventory.csv'
remove_files = False

# pulling user-input variables from command line
parser = argparse.ArgumentParser(description='rsync transfer to NEMO and mp4 conversion for sideview rigs')
parser.add_argument('-ip', '--ip_path', type=str, required=True, default=ip_path, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-e', '--experiment-name', type=str, required=True, help='name of experiment, will create a folder')
parser.add_argument('-c', '--condition', type=str, required=True, help='name of condition, will add to mp4')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, default=[], help='list of rig names')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-r', '--remove-files', action='store_true', help='whether to remove files from RPi source')
parser.add_argument('-j', '--job', dest='job', action='store', type=str, default=None, help='t=transfer, c=convert to mp4')
#parser.add_argument('-s', '--slurm-command', type=str, help='whether to remove files from RPi source')

# ingesting user-input arguments
args = parser.parse_args()
ip_path = args.ip_path
list_names = args.list_of_rig_names
username = args.username
experiment_name = args.experiment_name
experiment_name_base = os.path.basename(experiment_name)
condition = args.condition
job = args.job

#slurm_command = args.slurm_command

remove_files = args.remove_files

# change whether the input path is acceptable
if '/' not in experiment_name:
    raise ValueError("Error: double-check EXP_NAME, it should contain your username. For example, 'windinm/2024-12-03_sideview-exp1'")

# slurm-command and time
#print(f'Command used to submit this job: {slurm_command}')
print(f'Time started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

# save-path on NEMO
save_path = f'/camp/lab/windingm/home/users/{experiment_name}'
print(f'Save path is: {save_path}')

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

#########################
#### TRANSFER DATA ######
# transfer raw data from RPis to NEMO

start_transfer = datetime.now()

if 't' in job:
    print(f'Running rsync on {len(IPs)} IPs, {IPs}') 
    IPs_string = ' '.join(IPs)
    rig_num_str = [f'sv{x}' for x in rig_num]
    rigs_string = ' '.join(rig_num_str)

    # remove source files from RPi or not, is a user-input parameter
    if remove_files==True: remove_files_option = '--remove-source-files '  
    if remove_files==False: remove_files_option = '' 

    print('\nremove_files variable:')
    print(remove_files_option)
    print('\n')

    if len(IPs) == 0:
        print("No IP addresses found. Check your inventory.csv or filtering logic.")
        exit(1)

    if len(IPs) == 1:
        shell_script_content = f'''#!/bin/bash
    #SBATCH --job-name=rsync_pis
    #SBATCH --ntasks=1
    #SBATCH --cpus-per-task=16
    #SBATCH --partition=ncpu
    #SBATCH --mem=120G
    #SBATCH --time=20:00:00

    # Single IP setup
    IFS=' ' read -r -a ip_array <<< "{IPs_string}"
    IFS=' ' read -r -a rig_array <<< "{rigs_string}"

    # Directly assign the single IP and rig
    ip="${{ip_array[0]}}"
    rig="${{rig_array[0]}}"

    echo "Job started at: $(date)"
    echo "Using IP: $ip and Rig: $rig"

    # rsync using the single IP address
    rsync -avzhP {username}@$ip:/home/{username}/data/ {save_path}
    rsync -avzhP {remove_files_option}{username}@$ip:/home/{username}/data/ {save_path}
    rsync_status=$?

    # Check rsync status and output file if it fails
    if [ $rsync_status -ne 0 ]; then
        echo "Rsync failed for IP: $ip" > "FAILED-rsync_{experiment_name_base}_${{rig}}_IP-${{ip}}.out"
    fi

    ssh {username}@$ip "find data/ -mindepth 1 -type d -empty -delete"
    ssh {username}@$ip "sudo shutdown -h now"
    '''


    elif len(IPs) > 1:
        shell_script_content = f'''#!/bin/bash
    #SBATCH --job-name=rsync_pis
    #SBATCH --ntasks=1
    #SBATCH --cpus-per-task=16
    #SBATCH --partition=ncpu
    #SBATCH --mem=120G
    #SBATCH --time=20:00:00
    #SBATCH --array=1-{len(IPs)}

    # Multiple IP setup
    IFS=' ' read -r -a ip_array <<< "{IPs_string}"
    IFS=' ' read -r -a rig_array <<< "{rigs_string}"

    # Get the IP and rig for the current task ID
    ip="${{ip_array[$SLURM_ARRAY_TASK_ID-1]}}"
    rig="${{rig_array[$SLURM_ARRAY_TASK_ID-1]}}"

    echo "Job started at: $(date)"
    echo "Using IP: $ip and Rig: $rig"

    # rsync using the IP address for this task
    rsync -avzh --progress {username}@$ip:/home/{username}/data/ {save_path}
    rsync -avzh --progress {remove_files_option}{username}@$ip:/home/{username}/data/ {save_path}
    rsync_status=$?

    # Check rsync status and output file if it fails
    if [ $rsync_status -ne 0 ]; then
        echo "Rsync failed for IP: $ip" > "FAILED-rsync_{experiment_name_base}_${{rig}}_IP-${{ip}}.out"
    fi

    ssh {username}@$ip "find data/ -mindepth 1 -type d -empty -delete"
    ssh {username}@$ip "sudo shutdown -h now"
    '''

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
# originally adapted from Lucy Kimbley

start_processing = datetime.now()

if 'c' in job:


    def list_directory_contents(folder_path):
        # Check if the given path is a directory
        if not os.path.isdir(folder_path):
            print(f"{folder_path} is not a valid directory path.")
            return
        
        # Get the list of items in the directory
        contents = os.listdir(folder_path)
        
        return contents

    # generate and crop mp4 videos for each directory
    def run_commands_in_directory(path):
        # Define the commands

        # convert .h264 to .mp4
        # convert .h264 to .mp4 1fps, 30fps playback

        convert_mp4 = f'ffmpeg -i "{path}.h264" -c:v copy -c:a copy {path}_{condition}.mp4'
        convert_mp4_1fps = f'ffmpeg -i {path}_{condition}.mp4 -vf "fps=1" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -c:a copy {path}_{condition}_1fps.mp4'
        convert_mp4_30fps_playback = f'ffmpeg -i {path}_{condition}_1fps.mp4 -filter:v "setpts=PTS/24" -r 24 {path}_{condition}_1fps_24fps-playback.mp4'
        remove_h264 = f'rm {path}.h264'
        remove_mp4 = f'rm {path}_{condition}_1fps.mp4'

        # Run the commands using subprocess
        subprocess.run(convert_mp4, shell=True)
        subprocess.run(convert_mp4_1fps, shell=True)
        subprocess.run(convert_mp4_30fps_playback, shell=True)
        subprocess.run(remove_h264, shell=True)
        subprocess.run(remove_mp4, shell=True)

    # Path to the parent directory with the folders you want to list
    directory_contents = list_directory_contents(save_path)

    if directory_contents:
        print(f"Contents of {save_path}:")
        for item in directory_contents:
            print(item)
    else:
        print("No contents found.")

    if directory_contents:
        print(f"Processing each directory in {save_path}:")
        for file in directory_contents:
            if file.endswith('.h264'):
                print(f"\nProcessing: {save_path}/{file}")
                file = file.replace('.h264','')
                run_commands_in_directory(f'{save_path}/{file}')
    else:
        print("No directories found.")

if 'a' in job: # array-job transfer
    
    #### new bit using an array job to process the videos
    # Identify all .h264 files in the directory for array processing
    def list_directory_contents(folder_path):
        # Check if the given path is a directory
        if not os.path.isdir(folder_path):
            print(f"{folder_path} is not a valid directory path.")
            return
        
        # Get the list of items in the directory
        contents = os.listdir(folder_path)
        
        return contents

    directory_contents = list_directory_contents(save_path)

    h264_files = [f"{save_path}/{file.replace('.h264', '')}" for file in directory_contents if file.endswith('.h264')]
    h264_files_string = '\n'.join(h264_files)

    if len(h264_files) == 0:
        print("No .h264 files found in the directory. Ensure the save_path is correct and contains files.")
        exit(1)

    print(f'Running array job for mp4 conversion on:\n {h264_files_string}')

    # Array job script for processing each .h264 file
    process_script_content = f"""#!/bin/bash
    #SBATCH --job-name=sv_process
    #SBATCH --ntasks=1
    #SBATCH --cpus-per-task=32
    #SBATCH --array=1-{len(h264_files)}
    #SBATCH --partition=ncpu
    #SBATCH --mem=120G
    #SBATCH --time=10:00:00

    # Convert h264_files_string to an array
    IFS=$'\n' read -r -a files <<< "$(echo "{h264_files_string}" | tr ' ' '\n')"

    # Debugging info
    echo 'SLURM_ARRAY_TASK_ID: $SLURM_ARRAY_TASK_ID'
    echo 'Files array: ${{files[@]}}'

    # Assign file based on task ID
    file="${{files[$SLURM_ARRAY_TASK_ID-1]}}"
    echo "Processing file: $file"

    # Commands to process each file
    convert_mp4="ffmpeg -i \"${{file}}.h264\" -c:v copy -c:a copy \"${{file}}_{condition}.mp4\""
    convert_mp4_1fps="ffmpeg -i \"${{file}}_{condition}.mp4\" -vf 'fps=1' -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -c:a copy \"${{file}}_{condition}_1fps.mp4\""
    convert_mp4_30fps_playback="ffmpeg -i \"${{file}}_{condition}_1fps.mp4\" -filter:v 'setpts=PTS/24' -r 24 \"${{file}}_{condition}_1fps_24fps-playback.mp4\""
    remove_h264="rm \"${{file}}.h264\""
    remove_mp4="rm \"${{file}}_{condition}_1fps.mp4\""

    # Execute commands with error checks
    eval "$convert_mp4" || {{ echo "Failed at convert_mp4"; exit 1; }}
    eval "$convert_mp4_1fps" || {{ echo "Failed at convert_mp4_1fps"; exit 1; }}
    eval "$convert_mp4_30fps_playback" || {{ echo "Failed at convert_mp4_30fps_playback"; exit 1; }}
    eval "$remove_h264" || {{ echo "Failed at remove_h264"; exit 1; }}
    eval "$remove_mp4" || {{ echo "Failed at remove_mp4"; exit 1; }}

    echo "Finished processing file: $file"
    """

    print('sh file:')
    print(process_script_content)
    
    # Create a temporary file to hold the SBATCH script
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_process_script:
        tmp_process_script.write(process_script_content)
        tmp_process_script_path = tmp_process_script.name

    # Submit the SBATCH script
    process_submission = subprocess.run(["sbatch", tmp_process_script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Optionally, delete the temporary file after submission
    os.unlink(tmp_process_script_path)

    # Check the result and extract job ID from the output
    if process_submission.returncode == 0:
        process_job_id_output = process_submission.stdout.strip()
        print(process_job_id_output)

        process_job_id = process_job_id_output.split()[-1]

        print(process_submission.stdout)
    else:
        print("Failed to submit processing job array")
        print(process_submission.stderr)
        exit(1)

    seconds = 60
    print(f"Wait for {seconds} seconds before checking if array job has completed")
    time.sleep(seconds)

    print(f"Waiting for processing array job {process_job_id} to complete...")
    while not is_job_array_completed(process_job_id):
        print(f"Processing array job {process_job_id} is still running. Waiting...")
        time.sleep(30)  # Check every 30 seconds

    print(f"Processing array job {process_job_id} has completed.\n")
    
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
