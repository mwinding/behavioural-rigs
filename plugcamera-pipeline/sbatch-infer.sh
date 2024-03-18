#!/bin/bash

# usage: to run on pupae videos after unwrapping:
# sbatch --export=EXP_NAME=test_exp,RIG_NUMBERS="50 51 52",REMOVE=False sbatch-transfer.sh

#SBATCH --job-name=SLEAP_training
#SBATCH --ntasks=1
#SBATCH --time=08:00:00
#SBATCH --mem=64G
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=8
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate sleap
for video in "$VIDEOS_PATH"/*.jpg
do
  sleap-track "$video" -m 240306_235934.centroid -m 240306_235934.centered_instance
  sleap-convert "$video".predictions.slp -o "$video".json --format json
done
