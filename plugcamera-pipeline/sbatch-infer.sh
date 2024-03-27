#!/bin/bash

# usage: to run on pupae videos after unwrapping:
# sbatch --export=VIDEOS_PATH=path/to/videos,CENTROID_PATH=path/to/model.centroid,CENTERED_PATH=path/to/model.centered_instance sbatch-infer.sh

#SBATCH --job-name=SLEAP_infer
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
for video in "$VIDEOS_PATH"/*.mp4
do
  sleap-track "$video" -m "$CENTROID_PATH" -m "$CENTERED_PATH"
  #sleap-track "$video" -m 240306_235934.centroid -m 240306_235934.centered_instance
  sleap-convert "$video".predictions.slp -o "$video".json --format json
done
