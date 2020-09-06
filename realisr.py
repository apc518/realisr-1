print("timeplotter.py started")
print("importing modules...")

import os
import math
import random
import json

import matplotlib.pyplot as plt
from playsound import playsound

import wavparser as wp

class ClippingError(Exception):
	pass

class WalkPoint():
	def __init__(self, xval, yval):
		self.x = xval
		self.y = yval

	def __lt__(self, other):
		if self.x < other.x:
			return True
		else:
			return False

	def __str__(self):
		return "(" + str(self.x) + ", " + str(self.y) + ")"

	def __repr__(self):
		return "(" + str(self.x) + ", " + str(self.y) + ")"

def splitAudio(audio_data, segments=8, theta_multiplier=1, subdivisions=1):
	"""returns a tuple containing the pieces of audio and the associated random walk"""
	if type(audio_data) != list:
		raise TypeError("audio_data argument must be a list")
	if type(segments) != int:
		raise TypeError("segments argument must be an int")
	samples_per_segment = len(audio_data[0]) / segments
	split_audio = []
	for i in range(0, segments):
		current_segment = []
		for channel_idx in range(0, len(audio_data)):
			current_segment.append(audio_data[channel_idx][int(i * samples_per_segment):int((i+1) * samples_per_segment)])
		split_audio.append(current_segment)

	for _segment in split_audio:
		for channel in _segment:
			if len(channel) != len(_segment[0]):
				raise ValueError("different channel lengths..  bruh")
	return (split_audio, createRandomWalk(len(split_audio), theta_multiplier))

def splitByMeasure(audio_data, sample_rate=44100, tempo=120, beats_per_measure=4, theta_multiplier=1):
	# add null samples to the end of audio_data to make it a whole number of measures
	# then just call splitAudio with that number of measures
	samples_per_measure = sample_rate * beats_per_measure * 60 / tempo # float, not int
	for channel in audio_data:
		for i in range(0, int(len(channel) % samples_per_measure)):
			channel.append(0.0)
	return splitAudio(audio_data, int(len(audio_data[0]) / samples_per_measure), theta_multiplier=theta_multiplier)

def valueAtFloatIndex(lst, index):
	"""list argument must be a list of floats or integers"""
	if index == int(index):
		return lst[int(index)]
	else:
		# linear interpolation
		ceil_idx = math.ceil(index)
		floor_idx = math.floor(index)
		portion = index - floor_idx
		if ceil_idx > len(lst) - 1:
			ceil_idx = len(lst) - 1
		diff = lst[ceil_idx] - lst[floor_idx]
		return lst[floor_idx] + (portion*diff)

def changeSpeed(audio_data, speed=1):
	"""does not change speed in place, but returned a sped up/down version of the input"""
	if type(audio_data) != list:
		raise TypeError("audio_data argument must be a list")
	for channel in audio_data:
		if type(channel) != list:
			raise TypeError("audio_data must contain lists")
		if len(channel) != len(audio_data[0]):
			raise ValueError("all sublists of audio_data must be the same length")
	if not(type(speed) in [int, float]):
		raise TypeError("speed argument must be an int or float")
	if type(speed) == int:
		speed = float(speed)
	if speed == 0.0:
		raise ValueError("speed argument cannot be zero")
	abs_speed = abs(speed)
	original_total_samples = len(audio_data[0])
	product_total_samples = int(original_total_samples * (1/abs_speed))
	ret_audio = []
	for channel_idx in range(0, len(audio_data)):
		ret_audio.append([])
		for i in range(0, product_total_samples):
			if original_total_samples > 1:
				val = valueAtFloatIndex(audio_data[channel_idx], i*abs_speed)
			else:
				val = audio_data[channel_idx][0]
			ret_audio[channel_idx].append(val)
		if speed < 0:
			ret_audio[channel_idx].reverse()
	return ret_audio

def createRandomWalk(steps, theta_multiplier=1):
	"""returns a list of points with length steps+1"""
	initial_point = WalkPoint(0.0, 0.0)
	walkpoints = [initial_point]
	for i in range(0, steps):
		theta = random.uniform(0, 2*math.pi*theta_multiplier)
		if abs(theta - (math.pi / 2)) < 0.001 or abs(theta - (3*math.pi / 2)) < 0.001:
			theta += 0.001
		dx = random.uniform(1,2) * math.cos(theta)
		dy = random.uniform(1,2) * math.sin(theta)
		walkpoints.append(WalkPoint(walkpoints[i].x + dx, walkpoints[i].y + dy))
	return walkpoints

def findMax(audio_data):
	channel_maxes = []
	for channel in audio_data:
		peak = max(channel)
		low = min(channel)
		channel_max = max([abs(peak), abs(low)])
		channel_maxes.append(channel_max)
	return max(channel_maxes)

def normalized(audio_data, ceiling=1):
	"""the ceiling argument is the maximum absolute value for the samples after normalization"""
	if ceiling > 1 or ceiling < 0:
		ceiling == 1

	audio_max = findMax(audio_data)
	scale_factor = ceiling / audio_max

	ret_audio = []
	for channel_idx in range(0, len(audio_data)):
		ret_audio.append([])
		ret_audio[channel_idx] = [x * scale_factor for x in audio_data[channel_idx]]

	return ret_audio

def render(audio_data, theta_multiplier=0.5, tempo=120, beats_per_measure=4):
	update_progress("rendering...")
	"""
	audio_data_in should be a list of lists of floats
	"""
	walk_length = settings["walk_length"]
	sample_rate = settings["sample_rate"]
	falloff_power = settings["falloff_power"]
	theta_multiplier = settings["theta_multiplier"]
	tempo = settings["tempo"]
	beats_per_measure = settings["beats_per_measure"]

	# split the audio into segments
	update_progress("splitting audio...")
	if settings["split_by_measure"]:
		segments, random_walk = splitByMeasure(audio_data, sample_rate, tempo=tempo, beats_per_measure=beats_per_measure, theta_multiplier=theta_multiplier)
		walk_length = len(segments) # not necessary but important to be clear on
	else:
		segments, random_walk = splitAudio(audio_data, walk_length, theta_multiplier=theta_multiplier)

	# shift everything over so the minimum x value is 0
	x_offset = abs(min(random_walk).x)
	for i in range(0, len(random_walk)):
		random_walk[i].x += x_offset
	# calculate the cumulative projection (output audio) length in samples
	samples_per_segment = len(audio_data[0]) / len(segments)
	projection_length_in_samples = int(max(random_walk).x * samples_per_segment)

	segment_starting_points = [] # in samples
	segment_speeds = []
	segment_volume_maps = [] # a list of lists of floats describing a volume multiplier <= 1.0
	for i in range(0, len(segments)):
		# set segment speeds
		try:
			speed = 1 / (random_walk[i+1].x - random_walk[i].x)
		except ZeroDivisionError:
			# make speed greater than 2x the original number of samples in the segment
			# this means that the total resulting samples will be rounded to 0
			speed = len(segments[i][0]) * 3
		segment_speeds.append(speed)

		# set segment starting points
		if speed > 0:
			segment_starting_points.append(int(samples_per_segment * random_walk[i].x))
		elif speed < 0:
			segment_starting_points.append(int(samples_per_segment * random_walk[i+1].x))
		else:
			raise ValueError("A speed of 0 was encountered")

		if falloff_power != 0:
			volume_map = []
			for sample_idx in range(0, math.ceil(len(segments[i][0]) / abs(speed))):
				if random_walk[i].x < random_walk[i+1].x:
					x1 = random_walk[i].x
					x2 = random_walk[i+1].x
					y1 = random_walk[i].y
					y2 = random_walk[i+1].y
				else:
					x1 = random_walk[i+1].x
					x2 = random_walk[i].x
					y1 = random_walk[i+1].y
					y2 = random_walk[i].y
				slope = (y2 - y1) / (x2 - x1)
				x = (x2 - x1) * sample_idx / (math.ceil(len(segments[i][0]) / speed))
				y = slope * x + y1
				volume_multiplier = 1 / (abs(y) + 1)**falloff_power
				volume_map.append(volume_multiplier)
			segment_volume_maps.append(volume_map)

	projection = []
	# populate projection with 0s
	update_progress("creating base output audio...")
	for channel_idx in range(0, len(audio_data)):
		projection.append([])
		for i in range(0, projection_length_in_samples):
			projection[channel_idx].append(0.0)

	if settings["display_plot"]:
		update_progress("starting matplotlib display...")
		# matplotlib stuff to display the random walk, hooray!
		plt.style.use("fivethirtyeight")
		# apparently you need to do plt.ion() before plt.show() to prevent show() from blocking
		plt.ion()
		plt.show()
	update_progress("writing projected audio...")
	for seg_idx in range(0, len(segments)):
		if settings["display_plot"]:
			plt.plot([random_walk[seg_idx].x - x_offset, random_walk[seg_idx+1].x - x_offset], 
				[random_walk[seg_idx].y, random_walk[seg_idx+1].y])
			plt.draw()
			plt.pause(0.001)
		projected_segment = changeSpeed(segments[seg_idx], segment_speeds[seg_idx])
		for channel_idx in range(0, len(projection)):
			for i in range(0, len(projected_segment[0])):
				addition = projected_segment[channel_idx][i]
				if falloff_power != 0:
					addition *= segment_volume_maps[seg_idx][i]
				try:
					projection[channel_idx][i+segment_starting_points[seg_idx]] += addition
				except IndexError:
					update_progress("IndexError occurred")
	update_progress("normalizing...")
	return normalized(projection)

def getUserInput(prompt, type, error, numrange=(float("-inf"), float("inf")), inclusive=True):
	while True:
		try:
			value = type(input(prompt))
			if type in [int, float]:
				if inclusive:
					if value < numrange[0] or value > numrange[1]:
						print("value out of range")
						raise Exception()
				else:
					if value <= numrange[0] or value >= numrange[1]:
						print("value out of range")
						raise Exception()
			return value
		except:
			print(error)

def update_progress(message):
	jobid = settings["job_id"]
	print(f"timeplotter_{jobid}: " + message)
	if "jobs" in os.listdir():
		if not jobid in os.listdir("jobs"):
			open(f"jobs/{jobid}", "w")
		with open(f"jobs/{jobid}", "r+") as file:
			file.seek(0)
			file.write(message)
			file.truncate()

def process(inpath, outpath, jobid="default", splitbymeasure=False, walklength=8, tempo=120, beatspermeasure=4, displayplot=False, falloffpower=0, thetamultiplier=1):
	"""	this wraps up the entire functionality of the script in one function
		useful if you want to import this and use it from another script instead of
		running this directly with the CLI
	"""

	settings["split_by_measure"] = splitbymeasure
	settings["walk_length"] = walklength
	settings["tempo"] = tempo
	settings["beats_per_measure"] = beatspermeasure
	settings["display_plot"] = displayplot
	settings["falloff_power"] = falloffpower
	settings["theta_multiplier"] = thetamultiplier
	settings["job_id"] = jobid

	update_progress("parsing wave file...")
	sample_rate, audio_data = wp.parse(inpath)
	time_plot_projection = render(audio_data)
	update_progress("saving...")
	wp.save(time_plot_projection, outpath, samplerate=sample_rate)
	update_progress("finished processing.")

settings = json.loads(open("timeplotter_settings.json", "r").read())

if __name__ == "__main__":
	if not "output" in os.listdir():
		os.mkdir("output")

	filename = input("filename: ")
	if input("split by measure? ").lower() in ["yes", "y", "ye", "ys"]:
		settings["split_by_measure"] = True
	else:
		settings["split_by_measure"] = False
	if settings["split_by_measure"]:
		settings["tempo"] = getUserInput("beats per minute: ", float, 
			"please enter an int or float", (0, float("inf")), inclusive=False)
		if not(settings["assume_four_four"]):
			settings["beats_per_measure"] = getUserInput("beats per measure: ", float, 
				"please enter an int or float", (0, float("inf")), inclusive=False)
	else:
		settings["walk_length"] = getUserInput("segments: ", int, "please enter an int", (1, float("inf")), True)

	update_progress("parsing wav file...")
	sample_rate, audio = wp.parse(filename)
	time_plot_projection = render(audio)
	if "/" in filename:
		actual_filename = filename.rsplit("/", 1)[1]
	elif "\\" in filename:
		actual_filename = filename.rsplit("\\", 1)[1]
	else:
		actual_filename = filename
	save_path = wp.save(time_plot_projection, "output/" + actual_filename[:-4] + "_output", samplerate=sample_rate)
	playsound(save_path)
	input("Press enter to close program")