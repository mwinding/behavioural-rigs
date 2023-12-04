## Script to test batch connectivity to many IP addresses at once
# You will need to install `batch_pass`. If using macOS, run the following commands to 1) install homebrew and then 2) install sshpass:
#  1. /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#  2. brew install hudochenkov/sshpass/sshpass

import subprocess
import getpass
import pandas as pd
from datetime import datetime
import os

# import password from batch_pass.py, or type in the SSH password manually
try:
   from batch_pass import password
except:
   password = getpass.getpass("Enter the SSH password: ")

# IP address details, max seconds to test IP address
username = 'plugcamera'
IPs = ['10.7.195.18', '10.7.195.17']
timeout = 5

# record current time to save data
now = datetime.now()
now = now.strftime("%Y-%m-%d_%H-%M-%S")

# check how many IPs could be connected to
IPs_connected = []
for IP in IPs:
   ssh_command = f'sshpass -p "{password}" ssh -o ConnectTimeout={timeout} {username}@{IP} echo Connection Successful'
   result = subprocess.run(ssh_command, shell=True)

   if result.returncode == 0:
      print(f"Connection to {IP} successful")
      result = 1
   else:
      print(f"Failed to connect to {IP}")
      result = 0

   IPs_connected.append([IP, result])
   
# save the results to CSV
folder_path = 'data'

# Check if a data folder exists already and create it if not
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

# export data on SSH connectivity
IPs_connected = pd.DataFrame(IPs_connected, columns=['IP', 'SSH_worked'])
frac_connected = sum(IPs_connected.SSH_worked==1)/len(IPs_connected.SSH_worked)
IPs_connected.to_csv(f'{folder_path}/{now}_IPs-connected_{frac_connected:.0f}%.csv', index=0)

print(f'{frac_connected:.1f}% of IPs worked')