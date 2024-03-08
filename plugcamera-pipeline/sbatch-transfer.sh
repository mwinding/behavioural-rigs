#!/bin/bash

# usage: when transferring from plugcameras 50, 51, and 52 for example, use the following:
# sbatch --export=RIG_NUMBERS="50 51 52" sbatch-transfer.sh

#SBATCH --job-name=pc_transfer
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --mem=12G
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=8
#SBATCH --output=slurm-%j.out
#SBATCH --mail-user=$(whoami)@crick.ac.uk
#SBATCH --mail-type=FAIL

ml purge
ml Anaconda3/2023.09-0
ml FFmpeg/4.1-foss-2018b
source /camp/apps/eb/software/Anaconda/conda.env.sh

conda activate plugcamera-pipeline
#python -u transfer-data.py -ip ip_addresses.csv -e test_exp -l 41 42 43 > transfer_python-output.log 2>&1
python -u transfer-data.py -ip ip_addresses.csv -e test_exp -l $RIG_NUMBERS > python_output.log 2>&1