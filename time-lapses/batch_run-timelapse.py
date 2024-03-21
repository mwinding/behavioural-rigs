## Script to batch run a timelapse script (plug-camera_timelapse.py) to many IP addresses at once
# it will output a CSV file with information about connection success

# You will need to install `sshpass`. If using macOS, run the following commands to 1) install homebrew and then 2) install sshpass:
#  1. /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#  2. brew install hudochenkov/sshpass/sshpass

# Example usage (need to be updated)
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
import time

# default argument values
timeout = 10
username = 'plugcamera'
save_path = 'SSH_data'

# default arguments for plug-camera_timelapse.py
duration = 518400 # total time of timelapse, in seconds
interval = 600 # time between acquisitions, in seconds
experiment_name ='exp' # will create a folder with this name
focus_in_loop = False # do you autofocus before each capture, probably won't work for <3s intervals
sleep_time = 0 

# pulling user-input variables from command line
# note that the default timeout = 10 and default username = 'plugcamera' for SSH connections
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-p', '--ssh-password', type=str, required=True, help='SSH password')
parser.add_argument('-ip', '--ip_path', type=str, required=True, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, default=[], help='list of rig names')
parser.add_argument('-s', '--save-path', type=str, default=save_path, help='The path to save folder for SSH connectivity data')
parser.add_argument('-t', '--timeout', type=int, default=timeout, help='Number of seconds to attempt SSH connection')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-d', '--duration', type=int, default=duration, help='acquisition duration in seconds')
parser.add_argument('-i', '--interval', type=int, default=interval, help='acquisition interval between frames in seconds')
parser.add_argument('-e', '--experiment-name', type=str, required=True, default=experiment_name, help='name of experiment, will create a folder')
parser.add_argument('-f', '--focus-in-loop', type=bool, default=focus_in_loop, help='whether to run an autofocus cycle for each frame acquisition')
parser.add_argument('-sl', '--sleep-time', type=int, default=sleep_time, help='sleep time between triggering acquisitions on each RPi')

# ingesting user-input arguments
args = parser.parse_args()
password = args.ssh_password
ip_path = args.ip_path
list_names = args.list_of_rig_names
save_path = args.save_path
timeout = args.timeout
username = args.username
duration = args.duration
interval = args.interval
experiment_name = args.experiment_name
focus_in_loop = args.focus_in_loop
sleep_time = args.sleep_time

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

# record current time for naming the saved data CSV
now = datetime.now()
now = now.strftime("%Y-%m-%d_%H-%M-%S")

# check how many IPs could be connected to

print('\nTESTING SSH CONNECTIVITY...')
IPs_connected = []
for i, IP in enumerate(IPs):
    ssh_command = f'sshpass -p "{password}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout={timeout} {username}@{IP} echo Connection to {IP} successful'
    result = subprocess.run(ssh_command, shell=True)
    if result.returncode == 0:
        result = 1
    else:
        print(f"Failed to connect to 'pc{rig_num[i]}' [{IP}]")
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
print(f'{frac_connected*100:.1f}% of IPs worked\n')

###################
# run script on all RPis in batch
print('RUNNING TIMELAPSES...')
timings = ['']*len(IPs)
for i, IP in enumerate(IPs):
    try:
        print(f'Ran command on {rig_num[i]} [{IP}]')

        # pull the current time via local system and change Raspberry Pi time to that
        now = datetime.now()
        now = now.strftime("%m%d%H%M%Y.%S")
        time_command = f'sshpass -p {password} ssh {username}@{IP} "sudo date {now}"'
        result = subprocess.run(time_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        #print(f'Changed time to {now} on {rig_num[i]} [{IP}]')

        # check if the date actually changed and print the changed date
        check_time_command = f'sshpass -p {password} ssh {username}@{IP} "date"'
        result = subprocess.run(check_time_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # delete any old log files
        delete_log = f'sshpass -p {password} ssh {username}@{IP} "rm -f python.log"'
        subprocess.run(delete_log, shell=True, check=True)

        #print(f'Time is now {result.stdout}')

        # pull current time for folder naming
        now = datetime.now()
        now = now.strftime("%Y-%m-%d_%H-%M-%S")
        timings[i] = now

        # actually run the script to acquire timelapse data
        rig_name = f'pc{rig_num[i]}'
        run_script = f'nohup python plug-camera_timelapse.py -r {rig_name} -e {experiment_name} -d {duration} -i {interval} -f {focus_in_loop} -t {now} > python.log 2>&1 &'
        ssh_command = f'sshpass -p {password} ssh plugcamera@{IP} "{run_script}"'
        result = subprocess.run(ssh_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        time.sleep(sleep_time)

    except subprocess.CalledProcessError as e:
        print(f"Script failed on {rig_name} [{IP}] with error: {e.stderr.decode()}")
    except Exception as e:
        print(f"An error occurred on {rig_name} [{IP}]: {e}")
    except:
        print(f"Script failed on {rig_name} [{IP}]")

wait = 120
print(f'{wait}-second pause...\n')
time.sleep(wait)

print('TESTING WHETHER TIMELAPSES STARTED...')
for i, IP in enumerate(IPs):
    try:
        # check if RPi actually acquired an image
        now = timings[i]
        rig_name = f'pc{rig_num[i]}'
        
        check_script = f'ls /home/plugcamera/data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_image00000.jpg >/dev/null 2>&1 && echo "First image acquired on {rig_name} [{IP}]" || echo "No acquisition detected on {rig_name} [{IP}]!"'
        ssh_command = f'sshpass -p {password} ssh {username}@{IP} "{check_script}"'
        check_result = subprocess.run(ssh_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        feedback = check_result.stdout.decode().strip()
        #print(f'Checking: /home/plugcamera/data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_image00000.jpg')
        print(feedback)

        if(feedback==f"No acquisition detected on {rig_name} [{IP}]!"):
            ssh_command = f'sshpass -p {password} ssh {username}@{IP} cat python.log'
            check_result = subprocess.run(ssh_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = check_result.stdout.decode()
            for line in output.splitlines(): 
                print(f'\t{line}')
            print('')

    except subprocess.CalledProcessError as e:
        print(f"Script failed on {rig_name} [{IP}] with error: {e.stderr.decode()}")
    except Exception as e:
        print(f"An error occurred on {rig_name} [{IP}]: {e}")
    except:
        print(f"Script failed on {rig_name} [{IP}]")

print('')