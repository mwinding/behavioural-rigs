
import subprocess
import pandas as pd
from datetime import datetime
import os
import argparse
import time

# default argument values
username = 'plugcamera'
ip_path = 'ip_addresses.csv'

# pulling user-input variables from command line
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-ip', '--ip_path', type=str, required=True, default=ip_path, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-e', '--experiment-name', type=str, required=True, help='name of experiment, will create a folder')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, default=[], help='list of rig names')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')

# ingesting user-input arguments
args = parser.parse_args()
ip_path = args.ip_path
list_names = args.list_of_rig_names
username = args.username
experiment_name = args.experiment_name

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
if not os.path.exists(save_path):
    os.makedirs(save_path)

len(IPs)
IPs_string = ' '.join(IPs)

# shell script content
shell_script_content = f"""#!/bin/bash
#SBATCH --job-name=rsync_pis
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --array=1-{len(IPs)}
#SBATCH --partition=cpu
#SBATCH --mem=10G
#SBATCH --time=08:00:00

# convert ip_string to shell array
IFS=' ' read -r -a ip_array <<< "{IPs_string}"
ip_var="${{ip_array[$SLURM_ARRAY_TASK_ID-1]}}"

# rsync using the IP address obtained above

echo $ip_var

rsync -avzh --progress --remove-source-files plugcamera@$ip_var:/home/plugcamera/data/ /camp/lab/windingm/data/instruments/behavioural_rigs/plugcamera/data/2024-02-27_3hr-staging
ssh plugcamera@$ip_var "find data/ -mindepth 1 -type d -empty -delete"
"""
print(shell_script_content)

# Prepare the command to echo the shell script content and pipe it into `sbatch`
command = f'echo "{shell_script_content}" | sbatch'
print(command)

# Execute the command. Note: shell=True can be security-sensitive, ensure `shell_script_content` is trusted.
process = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Check the result
if process.returncode == 0:
    print("Successfully submitted job")
    print(process.stdout)
else:
    print("Failed to submit job")
    print(process.stderr)