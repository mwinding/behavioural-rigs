#!/bin/bash

# usage: when transferring from plugcameras 50, 51, and 52 for example, use the following:
# sbatch --export=JOB=tc,EXP_NAME=anna/2024-10-21_test-exp,CONDITION=TH-GAL4,RIG_NUMBERS="1 2 3",REMOVE=False sideview_sbatch-transfer.sh

#SBATCH --job-name=sv_transfer
#SBATCH --ntasks=1
#SBATCH --time=20:00:00
#SBATCH --mem=200G
#SBATCH --partition=ncpu
#SBATCH --cpus-per-task=32
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
ml FFmpeg/6.0-GCCcore-12.3.0
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate pyimagej-env

# echo -e "Command used to submit this job: sbatch $0 $@"
echo "Job started at: $(date)"

# Set JOB to ptc if not entered by user; p = predict, t = track, c = convert to feather output
: ${JOB:='tc'}

# Convert RIG_NUMBERS into an array
IFS=' ' read -r -a rig_numbers_array <<< "$RIG_NUMBERS"

# Construct the python command
python_cmd="python -u sideview_transfer-data.py -j "$JOB" -ip inventory.csv -e "$EXP_NAME" -c "$CONDITION" -l "${rig_numbers_array[@]}"" #-s "sbatch $0 $@"
if [ "$REMOVE" = "True" ]; then
    python_cmd="$python_cmd -r"
fi

BASENAME=$(basename "$EXP_NAME")

# Execute the python command
eval $python_cmd > python-output_"$BASENAME".log 2>&1