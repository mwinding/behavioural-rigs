## Script to test batch connectivity to many IP addresses at once
# it will output a CSV file with information about connection success

# You will need to install `sshpass`. If using macOS, run the following commands to 1) install homebrew and then 2) install sshpass:
#  1. /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#  2. brew install hudochenkov/sshpass/sshpass

# Example usage
# python batch_update-time.py -p [SSH_PASSWORD] -ip /path/to/IP_addresses.csv -l {rigname1} {rigname2} ...
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
username = 'topdown'

# pulling user-input variables from command line
# note that the default timeout = 10 and default username = 'plugcamera' for SSH connections
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-p', '--password', dest='ssh_password', action='store', type=str, required=True, help='SSH password')
parser.add_argument('-ip', '--ip-path', dest='ip_path', action='store', type=str, required=True, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-u', '--username', dest='username', action='store', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, default=[], help='list of rig names')

# ingesting user-input arguments
args = parser.parse_args()
password = args.ssh_password
ip_path = args.ip_path
username = args.username
list_names = args.list_of_rig_names

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

# check how many IPs could be connected to
IPs_connected = []
for i, IP in enumerate(IPs):
    ssh_command = f'sshpass -p "{password}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {username}@{IP} echo Connection to {IP} successful'
    result = subprocess.run(ssh_command, shell=True)
    if result.returncode == 0:
        result = 1
    else:
        print(f"Failed to connect to {IP}")
        result = 0
    IPs_connected.append([f'pc{rig_num[i]}', IP, result])

# report the total percent of IPs that could be reached by SSH
IPs_connected = pd.DataFrame(IPs_connected, columns=['rig_number','IP', 'SSH_worked'])
frac_connected = sum(IPs_connected.SSH_worked==1)/len(IPs_connected.SSH_worked)
print(f'{frac_connected*100:.1f}% of IPs worked')

#############################
# change time in batch
for i, IP in enumerate(IPs):
    try:
        # pull the current time via local system and change Raspberry Pi time to that
        now = datetime.now()
        now = now.strftime("%m%d%H%M%Y.%S")
        time_command = f'sshpass -p {password} ssh {username}@{IP} "sudo date {now}"'
        result = subprocess.run(time_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode())

    except subprocess.CalledProcessError as e:
        print(f"Script failed on {rig_num[i]} [{IP}] with error: {e.stderr.decode()}")
    except Exception as e:
        print(f"An error occurred on {rig_num[i]} [{IP}]: {e}")
    except:
        print(f"Script failed on {rig_num[i]} [{IP}]")