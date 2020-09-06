"""
pywavparser 0.3.0 by Andy Chamberlain
Free to use for any purpose without permission

"""

import os

autopath = False

class WavFormatException(Exception):
	pass
class ChannelException(Exception):
	pass

def find_fmt_offset(wav_bytes):
	fmt_index = 0
	for i in range(12, len(wav_bytes) - 4):
		if wav_bytes[i:i+4] == bytearray(b'fmt '):
			fmt_index = i
			break
	if fmt_index == 0:
		raise WavFormatException("Could not find \"fmt \" subchunk")
	return fmt_index - 12

def parse(filepath):
	"""returns the list of lists of floats which represents the wav file at filepath"""
	wav_file = open(filepath, "rb")
	wav_bytes = bytearray(wav_file.read())
	wav_file.close()
	if wav_bytes[0:4] != bytearray(b'RIFF') or wav_bytes[8:12] != bytearray(b'WAVE'):
		raise WavFormatException("Inputted file is not a valid wav file.")
	
	# because of the possibility of a JUNK chunk, we cannot assume 'fmt ' will be at index 12
	fmt_offset = find_fmt_offset(wav_bytes)
	if int.from_bytes(wav_bytes[20+fmt_offset:22+fmt_offset],'little',signed=False) != 1:
		raise WavFormatException("Invalid audio format. Must be uncompressed wav.")
	channel_num = int.from_bytes(wav_bytes[22+fmt_offset:24+fmt_offset],'little',signed=False)
	sample_rate = int.from_bytes(wav_bytes[24+fmt_offset:28+fmt_offset],'little',signed=False)
	bit_depth = int.from_bytes(wav_bytes[34+fmt_offset:36+fmt_offset],'little',signed=False)
	if bit_depth % 8 != 0:
		raise WavFormatException("Invalid bit depth. The inputted wav file has a bit depth which isn't divisible by 8.")
	slice_size = int(channel_num * bit_depth / 8)

	data_bytes_num = int.from_bytes(wav_bytes[40+fmt_offset:44+fmt_offset],'little',signed=False)

	wav_data = wav_bytes[44+fmt_offset:44+fmt_offset+data_bytes_num]
	
	byps = int(bit_depth / 8) # bytes per sample
	audio_data = [] # a list of lists, each sublist being a channel as a list of floats
	for i in range(0,channel_num):
		audio_data.append([])

	for i in range(0, int(len(wav_data) / (byps * channel_num))):
		for k in range(0,channel_num):
			intnum = int.from_bytes(wav_data[i*byps*channel_num + k*byps:i*byps*channel_num + k*byps + byps],'little',signed=True)
			audio_data[k].append(float(intnum / (2**(bit_depth-1) - 1)))

	return [sample_rate, audio_data]

def parseraw(filepath):
	"""returns only the audio data; no samplerate, no tuple"""
	return parse(filepath)[1]

def samplerate(filepath, bitdepth=False):
	wav_file = open(filepath, "rb")
	# read 128 bytes, if the format chunk isnt there then read the whole thing
	wav_bytes = bytearray(wav_file.read(128))
	if not(bytearray(b'fmt ') in wav_bytes):
		wav_bytes += bytearray(wav_file.read())
	wav_file.close()
	fmt_offset = find_fmt_offset(wav_bytes)
	if bitdepth:
		return int.from_bytes(wav_bytes[34+fmt_offset:36+fmt_offset],'little',signed=False)
	return int.from_bytes(wav_bytes[24+fmt_offset:28+fmt_offset],'little',signed=False)

def bitdepth(filepath):
	return samplerate(filepath, True)

def get_wav_bytes(audio_data, filepath=None, bitdepth=16, samplerate=44100):
	"""returns a wav file as a bytearray based on the inputted audio_data
	the audio_data must be a list of lists of floats"""
	if type(audio_data) != list:
		raise TypeError("The argument given was not a list")
	for lst in audio_data:
		if type(lst) != list:
			raise TypeError("The argument give was not a list of lists")
		for item in lst:
			if type(item) == int:
				item = float(item)
			elif type(item) != float:
				raise TypeError("Sublists must contain floats. Found a " + str(type(item)))
			if not(item >= -1.0 and item <= 1.0):
				raise ValueError("Values must be in range [-1.0, 1.0]")
	for lst in audio_data:
		if len(lst) != len(audio_data[0]):
			raise ChannelException("Not all channels are of equal length.")

	total_samples = len(audio_data) * len(audio_data[0])
	
	start_of_file = bytearray(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00D\xac\x00\x00\x10\xb1\x02\x00\x04\x00\x10\x00data')
	slicesize = int(len(audio_data) * bitdepth / 8)
	subchunk2size = int(total_samples*bitdepth/8)
	start_of_file = start_of_file[:4] + int(36+subchunk2size).to_bytes(4,'little',signed=False) + start_of_file[8:]
	start_of_file = start_of_file[:22] + len(audio_data).to_bytes(2,'little',signed=False) + samplerate.to_bytes(4,'little',signed=False) + int(samplerate * len(audio_data) * bitdepth / 8).to_bytes(4,'little',signed=False) + slicesize.to_bytes(2,'little',signed=False) + bitdepth.to_bytes(2,'little',signed=False) + start_of_file[36:]
	start_of_file += subchunk2size.to_bytes(4,'little',signed=False)
	wav_data = bytearray()
	for i in range(0, int(total_samples / len(audio_data))):
		for k in range(0, len(audio_data)):
			smpint = int(audio_data[k][i] * (2**(bitdepth-1) - 1))
			wav_data += (smpint.to_bytes(int(bitdepth/8),'little',signed=True))
	return start_of_file + wav_data

def save(audio_data, filepath=None, bitdepth=16, samplerate=44100):
	"""saves the bytes of a wav file to disk as an actual wav file"""
	wav_bytes = get_wav_bytes(audio_data, filepath, bitdepth, samplerate)

	if filepath == None:
		if not(autopath):
			raise ValueError("No filepath given. Try setting wavparser.autopath to true, or inputting a filepath in wavparser.save()")
		outfile_name = "wavparser_output_"
		outfile_num = 0
		while True:
			if outfile_name + str(outfile_num) + ".wav" in os.listdir():
				outfile_num += 1
			else:
				break
		file = open(outfile_name + str(outfile_num) + ".wav", "wb")
		file.write(wav_bytes)
		file.close()
		return outfile_name + str(outfile_num) + ".wav"
	else:
		if type(filepath) != str:
			raise TypeError("The given filepath was not a string")
		if filepath.endswith(".wav"):
			filepath = filepath[:-4]

		for i in range(1, len(filepath) + 1):
			if filepath[len(filepath) - i] in ["\\","/","\\\\"] or i == len(filepath):
				outfile_name = filepath[len(filepath) - i:]
				outfile_dir = filepath[:len(filepath) - i]
				break

		outfile_num = 1
		if outfile_name + ".wav" in os.listdir():
			while True:
				if outfile_name + " (" + str(outfile_num) + ")" ".wav" in os.listdir():
					outfile_num += 1
				else:
					break
			file = open(outfile_name + " (" + str(outfile_num) + ")" ".wav", "wb")
			file.write(wav_bytes)
			file.close()
			return outfile_name + " (" + str(outfile_num) + ")" ".wav"
		else:
			file = open(filepath + ".wav", "wb")
			file.write(wav_bytes)
			file.close()
			return filepath + ".wav"