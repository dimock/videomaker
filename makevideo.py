#!/usr/bin/python

import os, string, os.path, sys, re, argparse, subprocess, shutil, math
from datetime import datetime, timedelta

defaultProjectsFolder = ""
partPrefix = 'p'
videoExt = '.mp4'
videoWidth = 1920
videoHeight = 1080
audioSampleRate = 44100
videoCodec = "h264"
frameRate = 25
ffmpeg_name = "ffmpeg"
ffprobe_name = "ffprobe"
colorKey = "white"

with open( os.path.splitext(os.path.basename(__file__))[0] + ".cfg", "rt") as f:
  for line in f.readlines():
    p = line.split()
    for i in range(0, len(p), 2):
      x = p[i]
      if i+1 < len(p)-1:
        break
      key = x.lstrip().rstrip()
      value = p[i+1].lstrip().rstrip()
      if key == "PROJECTS_FOLDER":
        defaultProjectsFolder = value
      if key == "VIDEO_EXT":
        videoExt = value
      if key == "VIDEO_WIDTH":
        videoWidth = int(value)
      if key == "VIDEO_HEIGHT":
        videoHeight = int(value)
      if key == "AUDIO_SAMPLE_RATE":
        audioSampleRate = int(value)
      if key == "VIDEO_CODEC":
        videoCodec = value
      if key == "FRAME_RATE":
        frameRate = int(value)
      if key == "FFMPEG_NAME":
        ffmpeg_name = value
      if key == "FFPROBE_NAME":
        ffprobe_name = value
      if key == "COLOR_KEY":
        colorKey = value

parser = argparse.ArgumentParser("Simple video maker based on ffmpeg")
parser.add_argument('-s', help='Source moves folder', default="src", type=str, dest='sourceFolder')
parser.add_argument('-im', help='Images folder', default="images", type=str, dest='imagesFolder')
parser.add_argument('-sn', help='Sounds folder', default="sounds", type=str, dest='soundsFolder')
parser.add_argument('-w', help='Working folder', default="work", type=str, dest='workingFolder')
parser.add_argument('-pf', help='Projects folder', default=defaultProjectsFolder, type=str, dest='projectsFolder')
parser.add_argument('-pn', help='Project name', default='proj1', type=str, dest='projectName')
parser.add_argument('-o', help='Output moves folder', default="output", type=str, dest='outputFolder')
parser.add_argument('-of', help='Output file', default="ofile.mp4", type=str, dest='outputFile')
parser.add_argument('-mk', help='Make project with subfolders', action="store_true", dest='makeProject')
parser.add_argument('-mg', help='Merge all video parts', action="store_true", dest='mergeVideos')
parser.add_argument('-c', help='Cut all videos', action="store_true", dest='cutVideos')
parser.add_argument('-clean', help='Clean temporary video fragments in working folder', action="store_true", dest='cleanTemp')
parser.add_argument('-cpy', help='Copy source files from given folder according to project configuration', default="", type=str, dest='copyFolder')

args = parser.parse_args(sys.argv[1:])

projectFolder = os.path.join(args.projectsFolder, args.projectName)
imagesFolder = os.path.join(projectFolder, args.imagesFolder)
soundsFolder = os.path.join(projectFolder, args.soundsFolder)
sourceFolder = os.path.join(projectFolder, args.sourceFolder)
workingFolder = os.path.join(projectFolder, args.workingFolder)
outputFolder = os.path.join(projectFolder, args.outputFolder)
configFileName = os.path.join(projectFolder, args.projectName+'.cfg')
textsFileName = os.path.join(projectFolder, args.projectName+'.txt')

def make_project():
  if not os.path.exists(projectFolder):
    os.makedirs(projectFolder)
  if not os.path.exists(sourceFolder):
    os.makedirs(sourceFolder)
  if not os.path.exists(workingFolder):
    os.makedirs(workingFolder)
  if not os.path.exists(outputFolder):
    os.makedirs(outputFolder)
  if not os.path.exists(imagesFolder):
    os.makedirs(imagesFolder)
  if not os.path.exists(soundsFolder):
    os.makedirs(soundsFolder) 
  if not os.path.exists(configFileName):
    with open(configFileName, "wt") as f:
      f.write("# Write your project config here\n")
      f.write("#\n")
  if not os.path.exists(textsFileName):
    with open(textsFileName, "wt") as f:
      f.write("# Add texts here\n")
  print(f"Project {args.projectName} is created in {projectFolder}")

def read_time(s):
  try:
    ts = datetime.strptime(s, "%M:%S")
    dt = timedelta(minutes=ts.minute, seconds=ts.second)
    return float(dt.total_seconds())
  except ValueError as e:
    return float(s)

class FFText:
  text = ""
  tstart = 0.0
  tend = 0.0
  size0 = 24
  size1 = 24
  color = "white"
  x0 = 0.0
  y0 = 0.0
  x1 = 0.0
  y1 = 0.0
  alignv0 = 'c'
  alignh0 = 'c'
  alignv1 = 'c'
  alignh1 = 'c'
  fadet = 0.0

  def __init__(self, txt):
    self.text = txt

  def ffmpeg_filter(self, deltat):
    ts = self.tstart*deltat/100.0
    te = self.tend*deltat/100.0
    ta = ts + self.fadet
    tb = te - self.fadet
    if tb < ta:
      raise ValueError(f"{self.text} time incorrect. fade {self.fadet} > fragment time {deltat}")
    ft = self.fadet
    filter_strs = [f"drawtext=text='{self.text}'"]
    filter_strs += [f"fontcolor={self.color}"]
    if self.size1 == self.size0:
      filter_strs += [f"fontsize={self.size0}"]
    else:
      filter_strs += [f"fontsize={self.size0}+t*({self.size1}-{self.size0})/{deltat}"]
    if ft > 0:
      filter_strs += [f"alpha='if(lt(t,{ts}),0,if(lt(t,{ta}),(t-{ts})/{ft},if(lt(t,{tb}),1,if(lt(t,{te}),({tb}-t+{ft})/{ft},0))))'"]
    else:
      filter_strs += [f"alpha='if(lt(t,{ts}),0,if(lt(t,{te}),1,0))'"]
    x0 = float(self.x0)*0.01
    y0 = float(self.y0)*0.01
    x1 = float(self.x1)*0.01
    y1 = float(self.y1)*0.01
    vx0,vx1,vy0,vy1 = "","","",""
    if self.alignh0 == 'l':
      vx0 = f"w*{x0}"
    elif self.alignh0 == 'r':
      vx0 = f"(w*{x0}-text_w)"
    elif self.alignh0 == 'c':
      vx0 = f"(w*{x0}-text_w/2)"
    else:
      raise ValueError(f"incorrect horizontal alignment for x0 {self.alignh0} for {self.text}")
    if self.alignh1 == 'l':
      vx1 = f"w*{x1}"
    elif self.alignh1 == 'r':
      vx1 = f"(w*{x1}-text_w)"
    elif self.alignh1 == 'c':
      vx1 = f"(w*{x1}-text_w/2)"
    else:
      raise ValueError(f"incorrect horizontal alignment for x1 {self.alignh1} for {self.text}")
    if self.alignv0 == 'u':
      vy0 = f"h*{y0}"
    elif self.alignv0 == 'd':
      vy0 = f"(h*{y0}-text_h)"
    elif self.alignv0 == 'c':
      vy0 = f"(h*{y0}-text_h/2)"
    else:
      raise ValueError(f"incorrent vertical alignment for y0 {self.alignv0} for {self.text}")
    if self.alignv1 == 'u':
      vy1 = f"h*{y1}"
    elif self.alignv1 == 'd':
      vy1 = f"(h*{y1}-text_h)"
    elif self.alignv1 == 'c':
      vy1 = f"(h*{y1}-text_h/2)"
    else:
      raise ValueError(f"incorrent vertical alignment for y1 {self.alignv1} for {self.text}")
    filter_strs += [ f"x={vx0}+({vx1}-{vx0})*t/{deltat}" ]
    filter_strs += [ f"y={vy0}+({vy1}-{vy0})*t/{deltat}" ]
    filter_str = ':'.join(filter_strs)
    return filter_str

class FFSound:
  index = -1
  isound = -1
  tstart = 0.0
  tend = 0.0
  tfade = 0.0
  fname = ''
  svolume = 0.0
  istart = -1
  iend = -1
  sound_filter = ""
  voutname = ""
  aoutname = ""
  duration = 0.0
  asample_rate = audioSampleRate
  deltat = 0.0
  silent = False


  def parseAudioInfo(self):
    if not os.path.exists(self.fname):
      return
    p = subprocess.run([ffprobe_name, '-v', 'error', '-show_streams', self.fname], encoding='utf-8',stdout=subprocess.PIPE)
    streams_info = p.stdout.lstrip().rstrip().split('\n')
    streams = []
    for sval in streams_info:
      if sval == "[STREAM]":
        streams.append([])
        continue
      if len(streams) > 0:
        streams[-1].append(sval.split("="))
    for strm in streams:
     if len(list(filter(lambda x: len(x) > 1 and x[0].lstrip().rstrip() =="codec_type" and x[1].lstrip().rstrip() == "audio", strm))) > 0:
       for vals in strm:
        if len(vals) < 2:
          continue
        key, value = vals[0].lstrip().rstrip(), vals[1].lstrip().rstrip()
        if key == "sample_rate":
          self.asample_rate = int(value)
        if key == "duration":
          self.duration = math.floor(float(value))

  def update(self, nfiles, ffsnds_list, ffcmds_list):
    self.isound += nfiles
    self.deltat = 0.0
    for i in range(self.istart, self.iend):
      if ffcmds_list[i].create_out:
       self.deltat += ffcmds_list[i].deltat
    self.tend += self.deltat
 
  def __repr__(self):
    s = []
    keys = set()
    for k in vars(FFSound):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in vars(self):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in keys:
      v = getattr(self, k)
      s += [f"{k}={v}"]
    return f"{self.index}: " + " ".join(s)


  def ffmpeg_file(self):
    return ['-i', self.fname]

  def ffsilent_filter(self):
    self.aoutname = f"asnd{self.index}"
    self.sound_filter = f"anullsrc=r={self.asample_rate}:cl=stereo:d={self.deltat}[{self.aoutname}]"

  def ffmpeg_filter(self):
    if self.silent:
      self.ffsilent_filter()
      return
    asndname = f"asnd{self.index}"
    t0 = self.tstart
    t1 = self.tstart + self.tfade
    t2 = self.tend - self.tfade
    t3 = self.tend
    i = self.isound
    if t2 < t0:
      raise ValueError(f"audio time {t0} {t2} incorrect for {self.fname} at position {self.istart}")
    tt = []
    if self.tfade > 0:
      tt += [[t0, t1, 0.0, 1.0]]
    tt += [[t1, t2, 1.0, 1.0]]
    if self.tfade > 0:
      tt += [[t2, t3, 1.0, 0.0]]
    i = 0
    while i < len(tt):
      if tt[i][1] < tt[i][0]:
        raise ValueError(f"audio time segment {tt[i][0]} - {tt[i][1]} incorrect for {self.fname} at position {self.istart}")
      if tt[i][1]-tt[i][0]==0:
        del tt[i]
        continue
      if tt[i][0] >= self.duration:
        for j in range(i, len(tt)):
          tt[j][0] -= self.duration
          tt[j][1] -= self.duration
        continue
      if tt[i][1] > self.duration:
        t0 = tt[i][0]
        t1 = tt[i][1]
        v0 = tt[i][2]
        v1 = tt[i][3]
        vd = v0 + (v1 - v0) * (self.duration - t0) / (t1 - t0)
        del tt[i]
        tt.insert(i, [t0, self.duration, v0, vd])
        tt.insert(i+1, [0.0, t1-self.duration, vd, v1])
        for j in range(i+2, len(tt)):
          tt[j][0] -= duration
          tt[j][1] -= duration
      i += 1
    ffsnd_filters = []
    avnames = []
    for i, t in enumerate(tt):
      avname = f"asnd{self.index}_{i}"
      if len(tt) == 1:
        avname = asndname
      t0 = t[0]
      t1 = t[1]
      v0 = t[2]
      v1 = t[3]
      tfilters = [ f"[{self.isound}:a]atrim=start={t0}:end={t1},asetpts=PTS-STARTPTS,volume={self.svolume}" ]
      if v1 > v0:
        tfilters += [ f"afade=t=in:d={t1-t0}:silence={v0}:unity={v1}" ]
      elif v1 < v0:
        tfilters += [ f"afade=t=out:d={t1-t0}:silence={v1}:unity={v0}" ]
      ffsnd_filters += [ ",".join(tfilters) + f"[{avname}]" ]
      avnames += [ f"[{avname}]" ]
    if len(tt) > 1:
      ffsnd_filters += ["".join(avnames) + f"concat=n={len(avnames)}:v=0:a=1[{asndname}]"]
    self.aoutname = asndname
    self.sound_filter = ";".join(ffsnd_filters)

class FFBase:
  index = -1
  ifname = ""
  frate = 1.0
  volume = 0.0
  tstart = "00:00"
  tvideo = True
  width = videoWidth
  height = videoHeight
  iwidth = 0.0
  iheight = 0.0
  voutname = None
  aoutname = None
  cropw = 0
  croph = 0
  cropx = 0
  cropy = 0
  crop = False
  asample_rate= audioSampleRate
  vcodec = videoCodec

  def __init__(self, index, ifname, tvideo):
    self.index = index
    self.ifname = ifname
    self.tvideo = tvideo
 
  def parseVideoInfo(self, streams_info):
    streams = []
    for sval in streams_info:
      if sval == "[STREAM]":
        streams.append([])
        continue
      if len(streams) > 0:
        streams[-1].append(sval.split("="))
    for strm in streams:
      if len(list(filter(lambda x: len(x) > 1 and x[0].lstrip().rstrip() =="codec_type" and x[1].lstrip().rstrip() == "video", strm))) > 0:
        for vals in strm:
          if len(vals) < 2:
            continue
          key, value = vals[0].lstrip().rstrip(), vals[1].lstrip().rstrip()
          if key == "width":
            if self.tvideo:
              self.width = int(value)
            else:
              self.iwidth = int(value)
          if key == "height":
            if self.tvideo:
              self.height = int(value)
            else:
              self.iheight = int(value)
          if key == "codec_name":
            self.vcodec = value
      elif len(list(filter(lambda x: len(x) > 1 and x[0].lstrip().rstrip() =="codec_type" and x[1].lstrip().rstrip() == "audio", strm))) > 0:
        for vals in strm:
          if len(vals) < 2:
            continue
          key, value = vals[0].lstrip().rstrip(), vals[1].lstrip().rstrip()
          if key == "sample_rate":
            self.asample_rate = int(value)
 
class FFCmd(FFBase):
  fname = ''
  tdelta = ''
  deltat = 0.0
  volume = 1.0
  fadet = 0.0
  overlay = False
  fadeup = False
  fadedown = False
  create_out = True
  overlay_black = False
  video_filters = ""
  audio_filters = ""
  itexts = []
  texts = []
  tcolor = False
  color = ""

  def __init__(self, index, ifname, tvideo):
    super().__init__(index, ifname, tvideo)
    self.fname = os.path.join(workingFolder, partPrefix + "_" + str(self.index) + videoExt)
    if os.path.exists(self.ifname):
      p = subprocess.run([ffprobe_name, '-v', 'error', '-show_streams', self.ifname], encoding='utf-8',stdout=subprocess.PIPE)
      streams_info = p.stdout.lstrip().rstrip().split('\n')
      self.parseVideoInfo(streams_info)
 
  def __repr__(self):
    s = []
    keys = set()
    for k in vars(FFBase):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__') and k != 'texts':
        keys.add(k)
    for k in vars(FFCmd):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__') and k != 'texts':
        keys.add(k)
    for k in vars(self):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__') and k != 'texts':
        keys.add(k)
    for k in vars(super()):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__') and k != 'texts':
        keys.add(k)
    for k in keys:
      v = getattr(self, k)
      s += [f"{k}={v}"]
    return f"{self.index}: " + " ".join(s)

  def cut_video_part(self):
    if not self.tvideo:
      return
    cmdarr = [ffmpeg_name, '-ss', self.tstart,  '-i', self.ifname, '-c', 'copy', '-t', self.tdelta, self.fname]
    subprocess.run(cmdarr, cwd=projectFolder)


  def ffmpeg_filter(self):
    vname, aname =  f"vout{self.index}", f"aout{self.index}"
    ftype = 'in' if self.fadeup else 'out'
    video_filters = []
    audio_filters = []
    if self.tvideo:
      video_filters += [f"[{self.index}:v]setpts={1.0/self.frate}*PTS"]
      if self.crop:
        cw = int(self.width*self.cropw/100)
        ch = int(self.height*self.croph/100)
        cx = int(self.width*self.cropx/100)
        cy = int(self.height*self.cropy/100)
        video_filters += [f"crop={cw}:{ch}:{cx}:{cy}"]
        video_filters += [f"scale={self.width}:{self.height},setsar=1"]
      audio_filters += [f"[{self.index}:a]atempo={self.frate},volume={self.volume}"]
    elif self.tcolor:
      video_filters += [f"color={self.color}:s={self.width}x{self.height}:d={self.deltat},setsar=1"]
      audio_filters += [f"anullsrc=r={self.asample_rate}:cl=stereo:d={self.deltat}"]
    else: # image
      video_prefix = f"[{self.index}:v]"
      if self.crop:
        cw = int(self.iwidth*self.cropw/100)
        ch = int(self.iheight*self.croph/100)
        cx = int(self.iwidth*self.cropx/100)
        cy = int(self.iheight*self.cropy/100)
        video_filters += [f"{video_prefix}crop={cw}:{ch}:{cx}:{cy}"]
        video_prefix = ""
      video_filters += [f"{video_prefix}scale={self.width}:{self.height},setsar=1"]
      audio_filters += [f"anullsrc=r={self.asample_rate}:cl=stereo:d={self.deltat}"]
    vname1,aname1 = vname,aname
    for i in self.itexts:
      ftxt = self.texts[i]
      video_filters.append(ftxt.ffmpeg_filter(self.deltat))
    if self.fadeup or self.fadedown:
      video_filters += [f"fade=t={ftype}:alpha=1:d={self.fadet}"]
      audio_filters += [f"afade=t={ftype}:d={self.fadet}"]
    video_filters = [','.join(video_filters) + f"[{vname}]"]
    audio_filters = [','.join(audio_filters) + f"[{aname}]"]
    if self.overlay:
      video_filters += [f"[vout{self.index-1}][{vname}]overlay[{vname}]"]
      audio_filters += [f"[aout{self.index-1}][{aname}]acrossfade=d={self.fadet}[{aname}]"]
    elif self.overlay_black:
      bkgnd = f"bkgnd{self.index}"
      video_filters += [f"color=black:s={self.width}x{self.height}:d={self.fadet},setsar=1[{bkgnd}];[{bkgnd}][{vname}]overlay[{vname}]"]
    self.video_filters = ";".join(video_filters)
    self.audio_filters = ";".join(audio_filters)
    if self.create_out:
      self.voutname = vname
      self.aoutname = aname

  def ffmpeg_file(self):
    if self.tvideo:
      return ['-i', self.fname]
    elif not self.tcolor:
      return ['-loop', '1', '-t', f"{self.deltat}", "-i", self.ifname]
    else:
      return None

  def updateLast(self):
    self.fadedown = self.fadet > 0
    self.create_out = True
    self.overlay_black = self.fadedown


class FFOverlay(FFBase):
  frate = 1.0
  ovlx = 0 
  ovly = 0
  ovlw = 0
  ovlh = 0
  scale = False
  ioverlay = -1
  ioverlay_start = -1
  ioverlay_end = -1
  blank = False
  overlay_filters = ""

  def __init__(self, ifname, tvideo):
    super().__init__(-1, ifname, tvideo)
    if os.path.exists(ifname):
      p = subprocess.run([ffprobe_name, '-v', 'error', '-show_streams', self.ifname], encoding='utf-8',stdout=subprocess.PIPE)
      streams_info = p.stdout.lstrip().rstrip().split('\n')
      self.parseVideoInfo(streams_info)

  def __repr__(self):
    s = []
    keys = set()
    for k in vars(FFBase):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in vars(FFOverlay):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in vars(self):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in vars(super()):
      v = getattr(self, k)
      if not callable(v) and not k.startswith('__'):
        keys.add(k)
    for k in keys:
      v = getattr(self, k)
      s += [f"{k}={v}"]
    return f"{self.index}: " + " ".join(s)

  def ffmpeg_file(self):
    if self.tvideo:
      return ['-ss', self.tstart, '-i', self.ifname]
    else:
      return ['-loop', '1', '-t', f"{self.deltat}", "-i", self.ifname]

  def update(self, nfiles, ffoverlays_list, ffcmds_list):
    self.ioverlay += nfiles
    self.deltat = 0.0
    for i in range(self.ioverlay_start, self.ioverlay_end):
      if ffcmds_list[i].create_out:
        self.deltat += ffcmds_list[i].deltat
 
  def blank_filter(self):
    self.voutname = f"vovl{self.index}"
    self.overlay_filters = f"color={colorKey}:s={self.width}x{self.height}:d={self.deltat},setsar=1[{self.voutname}]"

  def ffmpeg_filter(self):
    if self.blank:
      self.blank_filter()
      return
    bkgnd = f"bkgnd{self.index}"
    deltat = self.deltat * self.frate
    vovlname = f"vovl{self.index}"
    filters_prefix = f"[{self.ioverlay}:v]"
    tmp_filters = []
    if self.tvideo:
      tmp_filters += [f"trim=start=0:end={deltat},setpts=(PTS-STARTPTS)*{1.0/self.frate}"]
    scale = self.scale
    sw,sh = 0,0
    if self.crop:
      if self.tvideo:
        cw = int(self.width*self.cropw/100)
        ch = int(self.height*self.croph/100)
        cx = int(self.width*self.cropx/100)
        cy = int(self.height*self.cropy/100)
      else:
        cw = int(self.iwidth*self.cropw/100)
        ch = int(self.iheight*self.croph/100)
        cx = int(self.iwidth*self.cropx/100)
        cy = int(self.iheight*self.cropy/100)
        sw = int(self.width*self.cropw/100)
        sh = int(self.height*self.croph/100)
        scale = True
      tmp_filters += [f"crop={cw}:{ch}:{cx}:{cy}"]
    if self.scale:
      sw = int(self.width*self.ovlw/100)
      sh = int(self.height*self.ovlh/100)
    if scale:
      tmp_filters += [f"scale={sw}:{sh}"]
    if not self.tvideo and not self.crop and not scale:
      tmp_filters += [f"scale={self.width}:{self.height}"]
    if not self.tvideo:
      tmp_filters += [f"setsar=1"]
    ox = int(self.ovlx*self.width/100)
    oy = int(self.ovly*self.height/100)
    filters = [filters_prefix +  ",".join(tmp_filters) + f"[{vovlname}]"]
    filters += [f"color={colorKey}:s={self.width}x{self.height}:d={self.deltat},setsar=1[{bkgnd}];[{bkgnd}][{vovlname}]overlay={ox}:{oy}[{vovlname}]"]
    self.overlay_filters = ";".join(filters)
    self.voutname = vovlname


def create_ffcmds(p, index, bfadet=0.0):
  index0 = 1
  fname = p[0]
  tcolor = False
  color = ""
  ifname = os.path.join(sourceFolder, fname)
  if fname == 'color':
    fname = ""
    ifname = ""
    index0 = 0
  frate = 1.0
  volume = 1.0
  fadet = 0.0
  fadeup = 0.0
  fadedown = 0.0
  ffcmds = []
  st0 = "00:00"
  st1 = "00:00"
  deltat = 0.0
  tvideo = True
  itexts = []
  cropw, croph, cropx, cropy = 0.0, 0.0, 0.0, 0.0
  crop = False
  overlay_prev = False
  for i in range(index0, len(p), 2):
    if i+1 > len(p)-1:
      break
    key = p[i]
    value = p[i+1]
    if key == 'color':
      tcolor = True
      tvideo = False
      color = value
    if key == 'dt':
      tvideo = False
      deltat = float(value)
    if key == 'ts':
      st0 = value
    if key == 'te':
      st1 = value
    if key == 'r':
      frate = float(value)
    if key == 'v':
      volume = float(value)
    if key == 'f':
      fadet = float(value)
    if key == 'u':
      fadeup = float(value)
    if key == 'd':
      fadedown = float(value)
    if key == 'text':
      itexts.append(int(value))
    if key == 'cropw':
      crop = True
      cropw = float(value)
    if key == 'croph':
      crop = True
      croph = float(value)
    if key == 'cropx':
      crop = True
      cropx = float(value)
    if key == 'cropy':
      crop = True
      cropy = float(value)
  if tcolor:
    crop = False
    tvideo = False
  if crop and (cropx < 0 or cropx + cropw > 100 or cropy < 0 or cropy + croph > 100):
    raise ValueError(f"{ifile} at {index} incorrect crop values {cropx} {cropy} {cropw} {croph}")
  if not tvideo:
    frate = 1.0
    if not tcolor:
      ifname = os.path.join(imagesFolder, fname)
  t0 = datetime.strptime(st0, "%M:%S")
  t1 = datetime.strptime(st1, "%M:%S")
  dt = t1 - t0
  if tvideo:
    deltat = dt.total_seconds()/frate
  else:
    dt = timedelta(seconds=deltat)
    t1 = t0 + dt
  if fadeup > 0:
    bfadet = fadeup
  if fadedown > 0:
    fadet = fadedown
  if fadet < 0:
    raise ValueError(f"incorrect fade time {fadet} for file {fname}")
  bfdt = timedelta(seconds=bfadet*frate)
  efdt = timedelta(seconds=fadet*frate)
  first = index == 0
  if bfadet > 0:
    ffcmd1 = FFCmd(index, ifname, tvideo)
    index += 1
    ffcmd1.fadet = bfadet
    ffcmd1.frate = frate
    ffcmd1.volume = volume
    ffcmd1.tstart = t0.strftime('%M:%S')
    ffcmd1.tdelta = ':'.join(str(bfdt).split(':')[1:])
    ffcmd1.deltat = bfdt.total_seconds()/frate
    ffcmd1.fadeup = bfadet > 0
    ffcmd1.overlay = not first and ffcmd1.fadeup
    ffcmd1.overlay_black = first and ffcmd1.fadeup
    ffcmd1.tvideo = tvideo
    ffcmd1.cropw = cropw
    ffcmd1.croph = croph
    ffcmd1.cropx = cropx
    ffcmd1.cropy = cropy
    ffcmd1.crop = crop
    ffcmd1.tcolor = tcolor
    ffcmd1.color = color
    ffcmds.append(ffcmd1)
  ffcmd2 = FFCmd(index, ifname, tvideo)
  index += 1
  ffcmd2.frate = frate
  ffcmd2.volume = volume
  ffcmd2.tstart = (t0 + bfdt).strftime('%M:%S')
  ffcmd2.itexts = itexts
  dt2 = dt - bfdt - efdt
  if dt2.total_seconds() < 0:
    print(f"fadet={fadet} bfadet={bfadet} dt={dt} t0={t0} t1={t1}")
    print(ffcmd2)
    raise ValueError(f"fragment duration {dt2.total_seconds()} is incorrect for {fname} at {index}")
  ffcmd2.tdelta =  ':'.join(str(dt2).split(':')[1:])
  ffcmd2.deltat = dt2.total_seconds()/frate
  ffcmd2.tvideo = tvideo
  ffcmd2.cropw = cropw
  ffcmd2.croph = croph
  ffcmd2.cropx = cropx
  ffcmd2.cropy = cropy
  ffcmd2.crop = crop
  ffcmd2.tcolor = tcolor
  ffcmd2.color = color
  ffcmds.append(ffcmd2)
  if fadet > 0:
    ffcmd3 = FFCmd(index, ifname, tvideo)
    index += 1
    ffcmd3.fadet = fadedown
    ffcmd3.frate = frate
    ffcmd3.volume = volume
    ffcmd3.tstart = (t1 - efdt).strftime('%M:%S')
    ffcmd3.tdelta = ':'.join(str(efdt).split(':')[1:])
    ffcmd3.deltat = efdt.total_seconds()/frate
    ffcmd3.tvideo = tvideo
    ffcmd3.create_out = False
    ffcmd3.cropw = cropw
    ffcmd3.croph = croph
    ffcmd3.cropx = cropx
    ffcmd3.cropy = cropy
    ffcmd3.crop = crop
    ffcmd3.tcolor = tcolor
    ffcmd3.color = color
    ffcmds.append(ffcmd3)
  return index, ffcmds, fadet

def create_ffsound(p, index):
  ffsnd = None
  tfade = 0.0
  volume = 0.0
  for i in range(1, len(p), 2):
    if p[i] == 'aend':
      return -1
    if i+1 >= len(p):
      break
    key = p[i]
    value = p[i+1]
    if key == 'ast':
      ffsnd = FFSound()
      ffsnd.tstart = ffsnd.tend = read_time(value)
    if key == 'sf':
      tfade = float(value)
    if key == 'v':
      volume = float(value)
  if ffsnd:
    ffsnd.tfade = tfade
    ffsnd.svolume = volume
    ffsnd.fname = os.path.join(soundsFolder, p[0])
    ffsnd.istart = index
    ffsnd.parseAudioInfo()
  return ffsnd
 
def create_ffoverlay(p, index):
  ffovl = None
  fname = p[0]
  tvideo = True
  tstart = None
  frate = 1.0
  cropw,croph,cropx,cropy, ovlx,ovly,ovlw,ovlh = 0.0,0.0,0.0,0.0, 0.0,0.0,0.0,0.0
  crop = False
  scale = False
  i = 1
  while i <  len(p):
    if p[i] == 'ovlend':
      return -1
    if p[i] == "ovlim":
      tvideo = False
      ifname = os.path.join(imagesFolder, fname)
      ffovl = FFOverlay(ifname, tvideo)
      i += 1
      continue
    if i+1 > len(p)-1:
      break
    key = p[i]
    value = p[i+1]
    i += 2
    if key == 'ovlts':
      tvideo = True
      ifname = os.path.join(sourceFolder, fname)
      ffovl = FFOverlay(ifname, tvideo)
      tstart = datetime.strptime(value, "%M:%S")
    if key == 'r':
      frate = float(value)
    if key == 'cropw':
      crop = True
      cropw = float(value)
    if key == 'croph':
      crop = True
      croph = float(value)
    if key == 'cropx':
      crop = True
      cropx = float(value)
    if key == 'cropy':
      crop = True
      cropy = float(value)
    if key == 'ovlx':
      ovlx = float(value)
    if key == 'ovly':
      ovly = float(value)
    if key == 'ovlw':
      scale = True
      ovlw = float(value)
    if key == 'ovlh':
      scale = True
      ovlh = float(value)
  if crop and (cropx < 0 or cropx + cropw > 100 or cropy < 0 or cropy + croph > 100):
    raise ValueError(f"{ifname} at {index} incorrect crop values {cropx} {cropy} {cropw} {croph}")
  if ovlx < 0 or ovlx + ovlw > 100 or ovly < 0 or ovly + ovlh > 100:
    raise ValueError(f"{ifname} at {index} incorrect overlay values {ovlx} {ovly}")
  if not ffovl:
    return None
  ffovl.frate = frate
  ffovl.volume = 0.0
  if tstart:
    ffovl.tstart = tstart.strftime('%M:%S')
  ffovl.tvideo = tvideo
  ffovl.cropw = cropw
  ffovl.croph = croph
  ffovl.cropx = cropx
  ffovl.cropy = cropy
  ffovl.crop = crop
  ffovl.ovlx = ovlx
  ffovl.ovly = ovly
  ffovl.ovlw = ovlw
  ffovl.ovlh = ovlh
  ffovl.scale = scale
  ffovl.ioverlay_start = index
  return ffovl
 
def load_texts():
  with open(textsFileName, 'rt') as f:
    lines = f.readlines()
  texts = []
  for line in lines:
    ltext = line.lstrip().rstrip()
    if len(ltext) == 0 or ltext[0] == '#':
      continue
    s = re.compile(r"([\'])(.*)([\'])(.*)", re.I).search(ltext)
    if not s:
      raise ValueError(f"error in texts file: {ltext}")
    ftxt = FFText(s.groups()[1].lstrip().rstrip())
    p = s.groups()[3].lstrip().rstrip().split()
    for i in range(0, len(p), 2):
      if i+1 > len(p)-1:
        break
      key = p[i]
      value = p[i+1]
      if key == 'ts':
        ftxt.tstart = float(value)
      if key == 'te':
        ftxt.tend = float(value)
      if key == 'size':
        ftxt.size0 = ftxt.size1 = int(value)
      if key == 'size0':
        ftxt.size0 = int(value)
      if key == 'size1':
        ftxt.size1 = int(value)
      if key == 'x':
        ftxt.x0 = ftxt.x1 = float(value)
      if key == 'y':
        ftxt.y0 = ftxt.y1 = float(value)
      if key == 'x0':
        ftxt.x0 = float(value)
      if key == 'y0':
        ftxt.y0 = float(value)
      if key == 'x1':
        ftxt.x1 = float(value)
      if key == 'y1':
        ftxt.y1 = float(value)
      if key == 'f':
        ftxt.fadet = float(value)
      if key == 'color':
        ftxt.color = value
      if key == 'av':
        ftxt.alignv0 = ftxt.alignv1 = value
      if key == 'ah':
        ftxt.alignh0 = ftxt.alignh1 = value
      if key == 'av0':
        ftxt.alignv0 = value
      if key == 'ah0':
        ftxt.alignh0 = value
      if key == 'av1':
        ftxt.alignv1 = value
      if key == 'ah1':
        ftxt.alignh1 = value
    texts.append(ftxt)
  return texts

def generate_ffcmds_list():
  texts = load_texts()
  index = 0
  fadet = 0.0
  isound = 0
  ioverlay = 0
  ffcmds_list = []
  ffsnds_list = []
  ffovls_list = []
  with open(configFileName, 'rt') as f:
    parsed = []
    for line in f.readlines():
      l = line.lstrip().rstrip()
      if len(l) == 0 or l[0] == '#':
        continue
      p = l.split()
      if len(p) == 0:
        continue
      parsed.append(p)
    for i, p in enumerate(parsed):
      s = create_ffsound(p, index)
      if s:
        if s == -1:
          ffsnd = ffsnds_list[-1]
          ffsnd.iend = index
        elif type(s) is FFSound:
          s.index = len(ffsnds_list)
          s.isound = isound
          isound += 1
          ffsnds_list.append(s)
        continue
      o = create_ffoverlay(p, index)
      if o:
        if o == -1:
          ffovl = ffovls_list[-1]
          ffovl.ioverlay_end = index
        elif type(o) is FFOverlay:
          o.index = len(ffovls_list)
          o.ioverlay = ioverlay
          ioverlay += 1
          ffovls_list.append(o)
        continue 
      r = create_ffcmds(p, index, fadet)
      index, ffcmds, fadet = r[0], r[1], r[2]
      ffcmds_list += ffcmds
    ffcmds_list[-1].updateLast()
  width = videoWidth
  height = videoHeight
  vcodec = videoCodec
  for ffcmd in ffcmds_list:
    if ffcmd.tvideo:
      width = ffcmd.width
      height = ffcmd.height
      break
  for ffcmd in ffcmds_list:
    ffcmd.texts = texts
    ffcmd.width = width
    ffcmd.height = height
    ffcmd.vcodec = vcodec
  for ffovl in ffovls_list:
    if ffovl.ioverlay_start < len(ffcmds_list) and ffcmds_list[ffovl.ioverlay_start].fadet > 0:
      ffovl.ioverlay_start += 1
    if ffovl.ioverlay_end > ffovl.ioverlay_start and ffovl.ioverlay_end-1 < len(ffcmds_list) and ffcmds_list[ffovl.ioverlay_end-1].fadet > 0:
      ffovl.ioverlay_end -= 1
  i = 0
  iprev = 0
  while i < len(ffovls_list):
    ffovl = ffovls_list[i]
    ffovl.width = width
    ffovl.height = height
    ffovl.vcodec = vcodec
    if ffovl.blank:
      raise IndexError(f"Overlays iteration error at {ffovl.index}. Should not be Blank")
    if ffovl.ioverlay_start > iprev:
      o = FFOverlay("", False)
      o.ioverlay_start = iprev
      o.ioverlay_end = ffovl.ioverlay_start
      iprev = ffovl.ioverlay_end
      o.blank = True
      o.width = width
      o.height = height
      ffovls_list.insert(i, o)
      i += 2
    else:
      i += 1
  if len(ffovls_list) > 0 and ffovls_list[-1].ioverlay_end < len(ffcmds_list):
    o = FFOverlay("", False)
    o.ioverlay_start = ffovl.ioverlay_end
    o.ioverlay_end = len(ffcmds_list)
    o.blank = True
    o.width = width
    o.height = height
    ffovls_list.append(o)
  i = 0
  iprev = 0
  while i < len(ffsnds_list):
    ffsnd = ffsnds_list[i]
    if ffsnd.silent:
      raise IndexError(f"Sounds iteration error at {ffsnd.index}. Should not be Silent")
    if ffsnd.istart > iprev:
      s = FFSound()
      s.istart = iprev
      s.iend = ffsnd.istart
      iprev = ffsnd.iend
      s.silent = True
      ffsnds_list.insert(i, s)
      i += 2
    else:
      i += 1
  if len(ffsnds_list) > 0 and ffsnds_list[-1].iend < len(ffcmds_list):
    s = FFSound()
    s.istart = ffsnd.iend
    s.iend = len(ffcmds_list)
    s.silent = True
    ffsnds_list.append(s)
  for i, ffsnd in enumerate(ffsnds_list):
    ffsnd.index = i
  for i, ffovl in enumerate(ffovls_list):
    ffovl.index = i
    ffovl.width = width
    ffovl.height = height
  return ffcmds_list, ffsnds_list, ffovls_list

def cut_all_videos():
  ffcmds_list, _, _ = generate_ffcmds_list()
  for ffcmd in ffcmds_list:
    ffcmd.cut_video_part()

def merge_all_videos(ofile):
  ffcmds_list, ffsnds_list, ffovls_list = generate_ffcmds_list()
  ffmpeg_cmds = [ffmpeg_name]
  ffmpeg_files = []
  ffmpeg_filters = []
  ffcmds_vanames = []
  ffsnds_anames = []
  ffovls_vnames = []
  total_deltat = 0.0
  width = videoWidth
  height = videoHeight
  nfiles = 0
  for ffcmd in ffcmds_list:
    if ffcmd.tvideo:
      width = ffcmd.width
      height = ffcmd.height
    if ffcmd.create_out:
      total_deltat += ffcmd.deltat
    ffcmd_file = ffcmd.ffmpeg_file()
    if ffcmd_file:
      ffmpeg_files += ffcmd_file
      nfiles += 1
    print(ffcmd)
  nsndfiles = 0
  sound_deltat = 0.0
  for i, ffsnd in enumerate(ffsnds_list):
    ffsnd.update(nfiles, ffsnds_list, ffcmds_list)
    if not ffsnd.silent:
      ffmpeg_files += ffsnd.ffmpeg_file()
      nsndfiles += 1
    sound_deltat += ffsnd.deltat
    print(ffsnd)
  nfiles += nsndfiles
  overlay_deltat = 0.0
  for i, ffovl in enumerate(ffovls_list):
    ffovl.update(nfiles, ffovls_list, ffcmds_list)
    if not ffovl.blank:
      ffmpeg_files += ffovl.ffmpeg_file()
    overlay_deltat += ffovl.deltat
    print(ffovl)
  if len(ffsnds_list) > 0 and total_deltat != sound_deltat:
    raise RuntimeError(f"Times of streams are different: total_deltat={total_deltat} sound_deltat={sound_deltat}")
  if len(ffovls_list) > 0 and  total_deltat != overlay_deltat:
    raise RuntimeError(f"Times of streams are different: total_deltat={total_deltat} overlay_deltat={overlay_deltat}")
  for i, ffcmd in enumerate(ffcmds_list):
    if i > 0 and ffcmd.overlay and ffcmds_list[i-1].create_out:
      raise RuntimeError(f"Incorrect overlay at {i}. previous fragment could not be overlayed")
    ffcmd.ffmpeg_filter()
    ffmpeg_filters.append(ffcmd.video_filters)
    ffmpeg_filters.append(ffcmd.audio_filters)
    if ffcmd.create_out:
      ffcmds_vanames.append(f"[{ffcmd.voutname}]")
      ffcmds_vanames.append(f"[{ffcmd.aoutname}]")
  for ffsnd in ffsnds_list:
    ffsnd.ffmpeg_filter()
    ffmpeg_filters.append(ffsnd.sound_filter)
    ffsnds_anames.append(f"[{ffsnd.aoutname}]")
  for ffovl in ffovls_list:
    ffovl.ffmpeg_filter()
    ffmpeg_filters.append(ffovl.overlay_filters)
    ffovls_vnames.append(f"[{ffovl.voutname}]")
  asndname = ""
  vovlname = ""
  if len(ffsnds_anames) > 0:
    n = len(ffsnds_anames)
    asndname = "asnd"
    ffsndconcat = ''.join(ffsnds_anames) + f"concat=n={n}:v=0:a=1[{asndname}]"
    ffmpeg_filters.append(ffsndconcat)
  if len(ffovls_vnames) > 0:
    n = len(ffovls_vnames)
    vovlname = "vovl"
    ffovlconcat = ''.join(ffovls_vnames) + f"concat=n={n}:v=1:a=0,colorkey={colorKey}[{vovlname}]"
    ffmpeg_filters.append(ffovlconcat)
  voutname,aoutname = "vout", "aout"
  n = len(ffcmds_vanames)//2
  fcmdconcat = ''.join(ffcmds_vanames) + f"concat=n={n}:v=1:a=1[{voutname}][{aoutname}]"
  ffmpeg_filters.append(fcmdconcat)
  if asndname != "":
    ffamixfilter = f"[{aoutname}][{asndname}]amix[{aoutname}]"
    ffmpeg_filters.append(ffamixfilter)
  if vovlname != "":
    ffvovlfilter = f"[{voutname}][{vovlname}]overlay[{voutname}]"
    ffmpeg_filters.append(ffvovlfilter)
  ffmpeg_cmds += ffmpeg_files
  filters_str = ';'.join(ffmpeg_filters)
  ffmpeg_cmds += ['-filter_complex', filters_str]
  ffmpeg_cmds += ['-map', f"[{voutname}]", '-map', f"[{aoutname}]", ofile]
#                  "-c:v", "libx265", "-an", "-x265-params", "crf=25", ofile]
  subprocess.run(ffmpeg_cmds, cwd=projectFolder)
  ffcmd_str =  " ".join(ffmpeg_cmds)
  print(ffcmd_str)
  print(f"total_deltat={total_deltat} sound_deltat={sound_deltat} overlay_deltat={overlay_deltat}")
#  with open("proj.sh", "wt") as f:
#    f.write(ffcmd_str)
 
def copySourceFiles(copyFolder):
  image_names = {}
  video_names = {}
  audio_names = {}
  ffcmds_list, ffsnds_list, ffovls_list = generate_ffcmds_list()
  for ffsnd in ffsnds_list:
    if len(ffsnd.fname) == 0 or ffsnd.silent:
      continue
    audio_names[os.path.basename(ffsnd.fname)] = ffsnd.fname
  for ffcmd in ffcmds_list:
    if len(ffcmd.ifname) == 0 or ffcmd.tcolor:
      continue
    if ffcmd.tvideo:
      video_names[os.path.basename(ffcmd.ifname)] = ffcmd.ifname
    else:
      image_names[os.path.basename(ffcmd.ifname)] = ffcmd.ifname
  for ffovl in ffovls_list:
    if len(ffovl.ifname) == 0 or ffovl.blank:
      continue
    if ffovl.tvideo:
      video_names[os.path.basename(ffovl.ifname)] = ffovl.ifname
    else:
      image_names[os.path.basename(ffovl.ifname)] = ffovl.ifname
  for (root_path, dirs, files) in os.walk(copyFolder):
    for file in files:
      if file in files:
        if file in image_names:
          if not os.path.exists(os.path.join(imagesFolder, file)):
            shutil.copy2(os.path.join(root_path, file), os.path.join(imagesFolder, file))
            print("copied to", os.path.join(imagesFolder, file))
        elif file in video_names:
          if not os.path.exists(os.path.join(sourceFolder, file)):
            shutil.copy2(os.path.join(root_path, file), os.path.join(sourceFolder, file))
            print("copied to", os.path.join(sourceFolder, file))
        elif file in audio_names:
          if not os.path.exists(os.path.join(soundsFolder, file)):
            shutil.copy2(os.path.join(root_path, file), os.path.join(soundsFolder, file))
            print("copied to", os.path.join(soundsFolder, file))
 

def cleanWorkingFolder():
  for file in filter(lambda x: os.path.splitext(x)[1] == videoExt, os.listdir(workingFolder)):
    print('delete', os.path.join(workingFolder, file))
    os.remove(os.path.join(workingFolder, file))

if __name__ == "__main__":
  try:
    if args.makeProject:
      make_project()
    if os.path.exists(args.copyFolder):
      copySourceFiles(args.copyFolder)
    if args.cleanTemp:
      cleanWorkingFolder()
    if args.cutVideos:
      cut_all_videos()
    if args.mergeVideos:
      merge_all_videos( os.path.join(outputFolder, args.outputFile) )
  except Exception as e:
    print("error: ", e)
