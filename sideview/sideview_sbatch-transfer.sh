#!/bin/bash

# usage: when transferring from plugcameras 50, 51, and 52 for example, use the following:
# sbatch --export=EXP_NAME=anna/2024-10-21_test-exp,RIG_NUMBERS="1 2 3",REMOVE=False sideview_sbatch-transfer.sh

#SBATCH --job-name=pc_transfer
#SBATCH --ntasks=1
#SBATCH --time=20:00:00
#SBATCH --mem=200G
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1  
#SBATCH --cpus-per-task=16
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
ml FFmpeg/4.1-foss-2018b
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate pyimagej-env

# Convert RIG_NUMBERS into an array
IFS=' ' read -r -a rig_numbers_array <<< "$RIG_NUMBERS"

# Construct the python command
python_cmd="python -u sideview_transfer-data.py -ip inventory.csv -e "$EXP_NAME" -l "${rig_numbers_array[@]}""
if [ "$REMOVE" = "True" ]; then
    python_cmd="$python_cmd -r"
fi

BASENAME=$(basename "$EXP_NAME")

# Execute the python command
eval $python_cmd > python-output_"$BASENAME".log 2>&1