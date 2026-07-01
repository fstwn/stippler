#! /usr/bin/env python3
import os
import sys
# ---------------------------------------------------------------------------
# Original images from http://mrl.nyu.edu/~ajsecord/
# -> http://cs.nyu.edu/~ajsecord/npar2002/StipplingOriginals.zip
# ---------------------------------------------------------------------------

cmd = sys.executable

os.system(cmd + " " + "-m stippler.classic../data/original/plant4h.png --save \
           --n_point 20000 --n_iter 50 --pointsize 1.5 1.5 --figsize 6 \
           --threshold 255 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/original/plant5_700x700.png  --save \
           --n_point 20000 --n_iter 50 --pointsize 2.5 2.5 --figsize 8 \
           --threshold 220 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/original/plant2_400x400.png  --save \
           --n_point 20000 --n_iter 50 --pointsize 1.0 1.0 --figsize 6 \
           --threshold 220 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/original/shoe_1300x1300_org.png  --save \
           --n_point 5000 --n_iter 50 --pointsize 6.0 6.0 --figsize 6 \
           --threshold 255 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/original/leaves_1024x1024_org.png  --save \
           --n_point 20000 --n_iter 50 --pointsize 3.0 3.0 --figsize 6 \
           --threshold 210 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/original/figure.png  --save \
           --n_point 1000 --n_iter 50 --pointsize 8 8 --figsize 6 \
           --force --interactive --threshold 240")

# ---------------------------------------------------------------------------
# These example use CC0 images
# ---------------------------------------------------------------------------
os.system(cmd + " " + "-m stippler.classic../data/boots.jpg --save  \
           --n_point 20000 --n_iter 50 --pointsize 2.5 5.0 --figsize 8 \
           --threshold 255 --force --interactive")

os.system(cmd + " " + "-m stippler.classic../data/pot-plant.jpg --save \
           --n_point 20000 --n_iter 50 --pointsize 2.0 4.0 --figsize 8 \
           --threshold 255 --force --interactive")

os.system (cmd + " " + "-m stippler.classic../data/leafs.jpg --save \
            --n_point 20000 --n_iter 50 --pointsize 2.0 4.0 --figsize 8 \
            --threshold 255 --force --interactive")
