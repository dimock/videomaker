# videomaker
Simple video maker script based on python and ffmpeg

1. Setup folder for all projects in makevideo.cfg
2. Create project: ./makevideo.py -pn <project_name> -mk
3. Go to project folder and add instructions to <project_name>.cfg
 example of cfg file:
 file1.mp4 ts 00:00 te 00:10 r 4 f 1 v 1.0
 file2.mp4 ts 01:15 te 01:30 r 2 f 0.5 v 0.0
  - ts - start time for fragment 00 min 00 sec
  - te - end time for fragment 00 min 10 sec
  - r - increase frame rate 4 times
  - f - fade time in seconds between this and next fragment
  - v - sound volume
4. Copy all video files (file1.mp4, ...) to <project_name>/src: ./makevideo.py -pn <project_name> -cpy <source_folder>
5. Create temp. video fragments: ./makervideo.py -pn <project_name> -c
6. Make output video file: ./makevideo.py -pn <project_name> -mg -of <output_video_name>
7. Result should be in project/output_folder
