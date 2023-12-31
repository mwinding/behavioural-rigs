## Script to test batch connectivity to many IP addresses at once
# it will output a CSV file with information about connection success

# You will need to install `sshpass`. If using macOS, run the following commands to 1) install homebrew and then 2) install sshpass:
#  1. /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#  2. brew install hudochenkov/sshpass/sshpass

# Example usage
# python batchSSH-test.py -p [SSH_PASSWORD] -i /path/to/IP_addresses.csv -s /path/to/save_folder
#
# optional arguments:   -t [timeout for SSH connections in seconds, default: 10]
#                       -u [username for SSH connections, default: 'plugcamera']

import subprocess
import getpass
import pandas as pd
from datetime import datetime
import os
import argparse

# default argument values
timeout = 10
username = 'plugcamera'
save_path = 'SSH_data'

# default arguments for plug-camera_timelapse.py
duration = 518400 # total time of timelapse, in seconds
interval = 600 # time between acquisitions, in seconds
experiment_name ='exp' # will create a folder with this name
focus_in_loop = False # do you autofocus before each capture, probably won't work for <3s intervals

# pulling user-input variables from command line
# note that the default timeout = 10 and default username = 'plugcamera' for SSH connections
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-p', '--password', dest='ssh_password', action='store', type=str, required=True, help='SSH password')
parser.add_argument('-ip', '--ip-path', dest='ip_path', action='store', type=str, required=True, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-s', '--save-path', dest='save_path', action='store', type=str, default=save_path, help='The path to save folder for SSH connectivity data')
parser.add_argument('-t', '--timeout', dest='timeout', action='store', type=int, default=timeout, help='Number of seconds to attempt SSH connection')
parser.add_argument('-u', '--username', dest='username', action='store', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-d', '--duration', dest='duration', action='store', type=int, default=duration, help='acquisition duration in seconds')
parser.add_argument('-i', '--interval', dest='interval', action='store', type=int, default=interval, help='acquisition interval between frames in seconds')
parser.add_argument('-e', '--experiment_name', dest='experiment_name', action='store', type=str, required=True, default=duration, help='name of experiment, will create a folder')
parser.add_argument('-f', '--focus-in-loop', dest='focus_in_loop', action='store', type=bool, default=focus_in_loop, help='whether to run an autofocus cycle for each frame acquisition')

# ingesting user-input arguments
args = parser.parse_args()
password = args.ssh_password
ip_path = args.ip_path
save_path = args.save_path
timeout = args.timeout
username = args.username
duration = args.duration
interval = args.interval
experiment_name = args.experiment_name
focus_in_loop = args.focus_in_loop

# pull IP address data
data = pd.read_csv(ip_path)
IPs = data.IP_address
rig_num = data.rig_number

# record current time for naming the saved data CSV
now = datetime.now()
now = now.strftime("%Y-%m-%d_%H-%M-%S")

# check how many IPs could be connected to
IPs_connected = []
for i, IP in enumerate(IPs):
    ssh_command = f'sshpass -p "{password}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout={timeout} {username}@{IP} echo Connection to {IP} successful'
    result = subprocess.run(ssh_command, shell=True)
    if result.returncode == 0:
        result = 1
    else:
        print(f"Failed to connect to {IP}")
        result = 0
    IPs_connected.append([f'pc{rig_num[i]}', IP, result])

# Check if a save folder exists already and create it if not
if not os.path.exists(save_path):
    os.makedirs(save_path)

# export data on SSH connectivity
IPs_connected = pd.DataFrame(IPs_connected, columns=['rig_number','IP', 'SSH_worked'])
frac_connected = sum(IPs_connected.SSH_worked==1)/len(IPs_connected.SSH_worked)
IPs_connected.to_csv(f'{save_path}/{now}_IPs-connected_{frac_connected*100:.0f}%.csv', index=0)

# report the total percent of IPs that could be reached by SSH
print(f'{frac_connected*100:.1f}% of IPs worked')

###################
# run script on all RPis in batch
for i, IP in enumerate(IPs):
    try:
        print(f'Running command on {IP}')
        run_script = f'nohup python plug-camera_timelapse.py -r pc{rig_num[i]} -e {experiment_name} -d {duration} -i {interval} -f {focus_in_loop} > /dev/null 2>&1 &'
        ssh_command = f'sshpass -p {password} ssh plugcamera@{IP} "{run_script}"'
        result = subprocess.run(ssh_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode())
    except subprocess.CalledProcessError as e:
        print(f"Script failed on {IP} with error: {e.stderr.decode()}")
    except Exception as e:
        print(f"An error occurred: {e}")
    except:
        print(f"Script failed {IP}")