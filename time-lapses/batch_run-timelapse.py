## Script to batch run a timelapse script (plug-camera_timelapse.py) to many IP addresses at once
# it will output a CSV file with information about connection success
# Optional retries will rerun only rigs whose acquisition did not start,
# restarting those RPis and waiting before each retry.
# If any attempt fails, a failure-history CSV is written to the save folder.
# If rigs still fail at the end, a final-failures CSV is also written.

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
import shlex

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
retries = 0
reboot_wait = 120

# pulling user-input variables from command line
# note that the default timeout = 10 and default username = 'plugcamera' for SSH connections
parser = argparse.ArgumentParser(description='Batch SSH test, requires SSH password, path of IP addresses to test, and a save path for the connectivity data')
parser.add_argument('-p', '--ssh-password', type=str, required=True, help='SSH password')
parser.add_argument('-ip', '--ip_path', type=str, required=True, help='The path to a CSV containing all IP_addresses')
parser.add_argument('-l', '--list-of-rig-names', nargs='+', type=int, required=False, default=[], help='list of rig names')
parser.add_argument('-s', '--save-path', type=str, default=save_path, help='The path to save folder for SSH connectivity data')
parser.add_argument('-t', '--timeout', type=int, default=timeout, help='Number of seconds to attempt SSH connection')
parser.add_argument('-u', '--username', type=str, default=username, help='username for SSH attempts')
parser.add_argument('-d', '--duration', type=int, default=duration, help='acquisition duration in seconds')
parser.add_argument('-i', '--interval', type=int, default=interval, help='acquisition interval between frames in seconds')
parser.add_argument('-e', '--experiment-name', type=str, required=True, default=experiment_name, help='name of experiment, will create a folder')
parser.add_argument('-f', '--focus-in-loop', type=bool, default=focus_in_loop, help='whether to run an autofocus cycle for each frame acquisition')
parser.add_argument('-sl', '--sleep-time', type=int, default=sleep_time, help='sleep time between triggering acquisitions on each RPi')
parser.add_argument('--retries', type=int, default=retries, help='number of times to retry failed acquisitions')
parser.add_argument('--reboot-wait', type=int, default=reboot_wait, help='seconds to wait after rebooting failed RPis before retrying')

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
retries = args.retries
reboot_wait = args.reboot_wait

if retries < 0:
    parser.error('--retries must be a non-negative integer')
if reboot_wait < 0:
    parser.error('--reboot-wait must be a non-negative integer')

# pull IP address data
data = pd.read_csv(ip_path)
IPs = data.IP_address
rig_num = data.rig_number

# only pulls IPs of interest and runs the script on those
if(len(list_names)>0):
    data.index = data.rig_number
    IPs = data.loc[list_names, 'IP_address'].values
    rig_num = list_names

IPs = list(IPs)
rig_num = list(rig_num)

# record current time for naming the saved data CSV
now = datetime.now()
now = now.strftime("%Y-%m-%d_%H-%M-%S")
batch_start = now

# check how many IPs could be connected to

print('\nTESTING SSH CONNECTIVITY...')
IPs_connected = []
for i, IP in enumerate(IPs):
    ssh_command = f'sshpass -p {shlex.quote(password)} ssh -o StrictHostKeyChecking=no -o ConnectTimeout={timeout} {username}@{IP} echo Connection to {IP} successful'
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
IPs_connected.to_csv(f'{save_path}/{batch_start}_IPs-connected_{frac_connected*100:.0f}%.csv', index=0)

# report the total percent of IPs that could be reached by SSH
print(f'{frac_connected*100:.1f}% of IPs worked\n')

timings = ['']*len(IPs)
failure_history = []

def run_remote(IP, remote_command, check=True):
    ssh_command = f'sshpass -p {shlex.quote(password)} ssh -o StrictHostKeyChecking=no -o ConnectTimeout={timeout} {username}@{IP} {shlex.quote(remote_command)}'
    return subprocess.run(ssh_command, shell=True, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def format_subprocess_error(e):
    err = e.stderr.decode(errors='replace').strip() if e.stderr else ''
    out = e.stdout.decode(errors='replace').strip() if e.stdout else ''
    return (err or out or str(e)).replace('\n', ' | ')

def read_python_log(IP):
    try:
        check_result = run_remote(IP, 'cat python.log')
        return check_result.stdout.decode(errors='replace')
    except subprocess.CalledProcessError as e:
        return f'Could not read python.log: {format_subprocess_error(e)}'
    except Exception as e:
        return f'Could not read python.log: {e}'

def add_failure(i, attempt, error, log_text=''):
    rig_name = f'pc{rig_num[i]}'
    experiment_folder = ''
    if timings[i] != '':
        experiment_folder = f'{timings[i]}_{rig_name}_{experiment_name}'

    failure_history.append([
        rig_num[i],
        IPs[i],
        attempt,
        error,
        experiment_folder,
        log_text
    ])

def launch_timelapse(i, attempt):
    IP = IPs[i]
    rig_name = f'pc{rig_num[i]}'

    try:
        print(f'Ran command on {rig_num[i]} [{IP}] (attempt {attempt})')

        if timings[i] == '':
            timings[i] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # pull the current time via local system and change Raspberry Pi time to that
        now = datetime.now().strftime("%m%d%H%M%Y.%S")
        result = run_remote(IP, f'sudo date {now}')

        #print(f'Changed time to {now} on {rig_num[i]} [{IP}]')

        # check if the date actually changed and print the changed date
        result = run_remote(IP, 'date')

        # delete any old log files
        run_remote(IP, 'rm -f python.log')

        #print(f'Time is now {result.stdout}')

        # use the first intended time for folder naming, including retries
        now = timings[i]

        # actually run the script to acquire timelapse data
        rig_name = f'pc{rig_num[i]}'
        run_script = f'nohup python plug-camera_timelapse.py -r {rig_name} -e {experiment_name} -d {duration} -i {interval} -f {focus_in_loop} -t {now} > python.log 2>&1 &'
        result = run_remote(IP, run_script)

        time.sleep(sleep_time)
        return True, ''

    except subprocess.CalledProcessError as e:
        err = format_subprocess_error(e)
        print(f"Script failed on {rig_name} [{IP}] with error: {err}")
        return False, f'LAUNCH_FAILED: {format_subprocess_error(e)}'
    except Exception as e:
        print(f"An error occurred on {rig_name} [{IP}]: {e}")
        return False, f'LAUNCH_ERROR: {e}'
    except:
        print(f"Script failed on {rig_name} [{IP}]")
        return False, 'LAUNCH_UNKNOWN_ERROR'

def check_timelapse_started(i, attempt):
    IP = IPs[i]
    rig_name = f'pc{rig_num[i]}'
    try:
        # check if RPi actually acquired an image
        now = timings[i]

        check_script = f'ls /home/plugcamera/data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_image00000.jpg >/dev/null 2>&1 && echo "First image acquired on {rig_name} [{IP}]" || echo "No acquisition detected on {rig_name} [{IP}]!"'
        check_result = run_remote(IP, check_script)
        feedback = check_result.stdout.decode().strip()
        #print(f'Checking: /home/plugcamera/data/{now}_{rig_name}_{experiment_name}/{now}_{rig_name}_{experiment_name}_image00000.jpg')
        print(feedback)

        if(feedback==f"No acquisition detected on {rig_name} [{IP}]!"):
            output = read_python_log(IP)
            for line in output.splitlines(): 
                print(f'\t{line}')
            print('')
            return False, 'NO_FIRST_IMAGE', output

        return True, '', ''

    except subprocess.CalledProcessError as e:
        err = format_subprocess_error(e)
        print(f"Script failed on {rig_name} [{IP}] with error: {err}")
        return False, f'CHECK_FAILED: {err}', ''
    except Exception as e:
        print(f"An error occurred on {rig_name} [{IP}]: {e}")
        return False, f'CHECK_ERROR: {e}', ''
    except:
        print(f"Script failed on {rig_name} [{IP}]")
        return False, 'CHECK_UNKNOWN_ERROR', ''

def restart_rig(i):
    IP = IPs[i]
    rig_name = f'pc{rig_num[i]}'
    print(f'Restarting {rig_name} [{IP}] before retry')
    try:
        run_remote(IP, 'pkill -f plug-camera_timelapse.py || true', check=False)
        run_remote(IP, 'sudo shutdown -r now', check=False)
    except Exception as e:
        print(f'\tCould not restart {rig_name} [{IP}]: {e}')

###################
# run script on all RPis in batch
rounds = retries + 1
to_process = list(range(len(IPs)))

for attempt in range(1, rounds + 1):
    if len(to_process) == 0:
        break

    if attempt > 1:
        print(f'\nRESTARTING FAILED RPIS BEFORE ATTEMPT {attempt}/{rounds}...')
        for i in to_process:
            restart_rig(i)

        print(f'{reboot_wait}-second pause for RPis to restart...\n')
        time.sleep(reboot_wait)

    print(f'RUNNING TIMELAPSES... ATTEMPT {attempt}/{rounds}')
    launched = []
    next_fail = []
    for i in to_process:
        worked, error = launch_timelapse(i, attempt)
        if worked:
            launched.append(i)
        else:
            add_failure(i, attempt, error)
            next_fail.append(i)

    if len(launched) > 0:
        wait = 120
        print(f'{wait}-second pause...\n')
        time.sleep(wait)

        print('TESTING WHETHER TIMELAPSES STARTED...')
        for i in launched:
            worked, error, log_text = check_timelapse_started(i, attempt)
            if not worked:
                add_failure(i, attempt, error, log_text)
                next_fail.append(i)

    to_process = next_fail

print('')

if len(failure_history) > 0:
    failures = pd.DataFrame(failure_history, columns=['rig_number', 'IP_address', 'attempt', 'error', 'experiment_folder', 'log'])
    failure_path = f'{save_path}/{batch_start}_timelapse-failure-history.csv'
    failures.to_csv(failure_path, index=0)
    print(f'Failure history written to: {failure_path}')

if len(to_process) > 0:
    final_failures = []
    for i in to_process:
        final_failures.append([rig_num[i], IPs[i]])
    final_failures = pd.DataFrame(final_failures, columns=['rig_number', 'IP_address'])
    final_failure_path = f'{save_path}/{batch_start}_timelapse-final-failures.csv'
    final_failures.to_csv(final_failure_path, index=0)

    print(f'{len(to_process)} rig(s) still failed after {rounds} attempt(s).')
    print(f'Final failures written to: {final_failure_path}')
else:
    print(f'All timelapses started successfully after up to {rounds} attempt(s).')
