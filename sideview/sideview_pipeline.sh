#!/bin/bash

# usage: when transferring from plugcameras 50, 51, and 52 for example, use the following:
# sbatch --export=EXP=anna/2024-10-21_test-exp,CON="group-housed",RIGS="1 2 3",REMOVE=True,MODEL='sideview',JOB='pcb' sideview_pipeline.sh

# Usage: sbatch --export=MODEL="sideview",JOB="pcd" sleap-track_batch.sh
# optional parameters: sbatch --export=MODEL="sideview",JOB='ptcd',TRACK="False",FRAMES="0-10" sleap-track_batch.sh
# for JOB, p = predict with SLEAP, t = track with SLEAP, c = convert .slp to .feather, and d = DSCAN clustering

# *** MAKE SURE TO USE A REMOTELY-TRAINED MODEL!!!! ***
# we have experienced issues with locally trained models running remotely...

#SBATCH --job-name=slp-master
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --partition=ncpu
#SBATCH --mem=400G
#SBATCH --time=48:00:00
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL


ml purge
ml Anaconda3/2023.09-0
ml FFmpeg/6.0-GCCcore-12.3.0
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate /camp/lab/windingm/home/shared/conda-envs/sleap #use shared conda env on NEMO

##### STEP 1: TRANSFER DATA AND CONVERT TO MP4 #######
######################################################

# Convert RIG_NUMBERS into an array
IFS=' ' read -r -a rig_numbers_array <<< "$RIGS"

# Construct the python command
python_cmd="python -u sideview_transfer-data.py -ip inventory.csv -e "$EXP" -c "$CON" -l "${rig_numbers_array[@]}""
if [ "$REMOVE" = "True" ]; then
    python_cmd="$python_cmd -r"
fi

BASENAME=$(basename "$EXP")

# Execute the python command
eval $python_cmd > python-output_"$BASENAME".log 2>&1


##### STEP 2: SLEAP PREDICTIONS, FEATHER CONVERSION, DBSCAN CLUSTERING #######
##############################################################################

# directory with mp4s within
DIR="/camp/lab/windingm/data/instruments/behavioural_rigs/${MODEL}/${EXP}"

# Set TRACK to True if not entered by user
: ${TRACK:='True'}

# Set FRAMES to all if not entered by user
: ${FRAMES:='all'}

# Set JOB to ptc if not entered by user; p = predict, t = track, c = convert to feather output
: ${JOB:='ptc'}

echo "model type: $MODEL"
echo "videos directory path: $DIR"
echo "jobs, p=prediction, t=track, c=convert to feather: $JOB"
echo "frames: $FRAMES"

# run python script
# save output to log file in case there is an issue
# adding -u makes sure the python_output.log is dynamically written to
cmd="python -u /camp/lab/windingm/home/shared/Crick-HPC-files/sbatch-files/sleap-track_batch.py -m "$MODEL" -p "$DIR" -j "$JOB" -f "$FRAMES"" 
eval $cmd > python_output.log 2>&1