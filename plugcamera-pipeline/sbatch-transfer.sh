#!/bin/bash

#SBATCH --job-name=transfer-data
#SBATCH --ntasks=1
#SBATCH --time=0:00:00
#SBATCH --mem=12G
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate plugcamera-pipeline
bash transfer-data.sh