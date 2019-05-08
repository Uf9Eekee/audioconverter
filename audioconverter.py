#Collects uncompressed WAVE files and converts them to various compressed formats
#using FFmpeg via the ffmpy command line wrapper. Collects metadata and appends
#it to the files, and finally organizes the finished files into a zip file
#with each conversion in a separate folder, ready for downloading.

#The use case for this is audio engineers delivering files to an end customer,
#where conversion into various formats is in their job description, but often not
#part of their core expertise, which makes this task ideal for automation.

import os, shutil, ffmpy, mutagen, zipfile, sys
from datetime import datetime
from os.path import isfile, join
from os import listdir
from mutagen.id3 import ID3, TIT2
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.aac import AAC
from flask import Flask, Response, request, send_file, render_template, redirect
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024
app.config["FILE_UPLOAD_MAX_MEMORY_SIZE"] = 4 * 1024 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["ARCHIVE_FOLDER"] = "archived"
app.config["FINISHED_PROJECTS"] = "finished"

#Returns the entry page where files are selected for uploading.
@app.route("/", methods=["GET"])
def entry_page():
	return render_template("postfile.html")

#Returns metadata input for a particular project.
@app.route("/project/<project>", methods=["GET"])
def input_metadata(project):
	filepath=app.config["UPLOAD_FOLDER"] + "/" + project
	if os.path.isdir(filepath):
		files = sorted(os.listdir(app.config["UPLOAD_FOLDER"] + "/" + project + "/flac/"))
		return render_template("addmetadata.html", tracks = files, project = project)
	return Response("Project does not exist!", mimetype="text/plain")
#Collects the metadata from the collection form and refers to add_track_metadata
@app.route("/postmetadata", methods=["POST"])
def add_metadata():
	album_title = request.form.get("album_title")
	album_artist = request.form.get("album_artist")
	copyright_message = request.form.get("copyright_message")
	release_date = request.form.get("release_date")
	tracks = request.form.getlist("track")
	project = request.form.get("project")
	print tracks
	for track in tracks:
		track_title = request.form.get(track + "_title")
		track_composer = request.form.get(track + "_composer")
		track_isrc = request.form.get(track + "_isrc")
		track_filename = track
		add_track_metadata(project, track_filename, album_title, album_artist, release_date, copyright_message, track_title, track_composer, track_isrc)
	convert_to_misc(project)
	url = package_project(project)
	
	return redirect(url)

#Collects the files for conversion. Expects WAV files. Checks for this by MIME type. It expects
#the files to be named XX_trackname.wav, where XX is the track number, and trackname is the name
#of the track.
@app.route("/upload", methods=["POST"])
def fileupload():

	if 'masters' not in request.files:
		return Response("No file submitted!", mimetype="text/plain")

	if 'projectname' not in request.values:
		return Response("No project name submitted!", mimetype="text/plain")

	projectname = request.values.get("projectname")
	filepath = app.config["UPLOAD_FOLDER"] + "/" + projectname

	if os.path.isdir(filepath):
		return Response("Project with the same name already exists! Pick a new name or delete existing project.", mimetype="text/plain")
	
	os.mkdir(filepath)

	for f in request.files.getlist("masters"):
		file = f
		filename = secure_filename(file.filename)
		mimetype = file.mimetype.encode("utf-8")
		if filename[-4:] != ".wav":
			return Response("Incorrect file extension of " + filename + ", expected .wav!", mimetype="text/plain")
		if mimetype != "audio/x-wav" and mimetype != "audio/wav" and mimetype != "audio/wave":
			shutil.rmtree(filepath)
			return Response("Mimetype of " + filename + " indicates it's not really a wav file!", mimetype="text/plain")

		file.stream.seek(0)
		file.save(os.path.join(filepath, filename))
	convert_to_flac(projectname)
	return redirect("/project/" + projectname)

#Converts the WAV files into FLAC versions, which are the files that the metadata is later added to. Existing
#metadata is stripped.
def convert_to_flac(projectname):
	directory = app.config["UPLOAD_FOLDER"] + "/" + projectname
	files = os.listdir(directory)
	flac_filepath = directory + "/flac/"
	os.mkdir(flac_filepath)
	for wav in files:
		filepath = directory + "/" + wav
		ff = ffmpy.FFmpeg(
		inputs={filepath: None},
		outputs={flac_filepath + wav[:-4] + ".flac": ["-sample_fmt", "s16", "-map_metadata", "-1"]}
		)
		ff.cmd
		ff.run()

#Converts the FLAC files (now with the correct metadata) into other formats. The metadata is preserved
#by FFmpeg. This way, the metadata is only added once.
def convert_to_misc(projectname):
	directory = app.config["UPLOAD_FOLDER"] + "/" + projectname

	flac_filepath = directory + "/flac/"
	mp3_filepath = directory + "/mp3_320/"
	aac_filepath = directory + "/aac_256/"
	ogg_filepath = directory + "/ogg/"
	opus_filepath = directory + "/opus/"
	
	tracks = os.listdir(flac_filepath)
	
	

	os.mkdir(mp3_filepath)
	os.mkdir(aac_filepath)
	os.mkdir(ogg_filepath)
	os.mkdir(opus_filepath)

	for track in tracks:
		filepath = directory + "/flac/" + track
		ff = ffmpy.FFmpeg(

		inputs={filepath: None},
		outputs={
			mp3_filepath + track[:-5] + ".mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
			aac_filepath + track[:-5] + ".aac": ["-c:a", "aac", "-b:a", "256k"],
			ogg_filepath + track[:-5] + ".ogg": ["-c:a", "libvorbis", "-q:a", "4"],
			opus_filepath + track[:-5] +".opus": ["-c:a", "libopus", "-b:a","128k"]
			}
		)
		
		ff.cmd
		ff.run()
#Adds the track metadata to the the file.
def add_track_metadata(project, track_filename, album_title, album_artist, album_date, copyright_message, track_title, track_composer, track_isrc):
	flac_directory = (app.config["UPLOAD_FOLDER"] + "/" + project + "/flac/").encode("ascii", "ignore")

	track = FLAC(flac_directory + track_filename.encode("ascii", "ignore"))
	track["ALBUM"] = album_title
	track["ARTIST"] = album_artist
	track["COPYRIGHT"] = track_composer
	track["LICENCE"] = copyright_message
	track["TITLE"] = track_title
	track["ISRC"] = track_isrc
	track["DATE"] = album_date
	track["TRACKNUMBER"] = track_filename[:2]
	
	track.save()
#Packages the project into archive, which has the initially uploaded 24 bit wav, into the archive, and
#packages the compressed files into the finished folder, returning a path to the finished zip file.
def package_project(project):
	project_directory = app.config["UPLOAD_FOLDER"] + "/" + project + "/"
	finished_path = app.config["FINISHED_PROJECTS"] + "/" + project + "/"
	archive_name = str(datetime.now()) + "_" + project
	archive_path = app.config["ARCHIVE_FOLDER"] + "/" + str(datetime.now()) + project + "/"
	os.mkdir(archive_path)
	os.mkdir(finished_path)
	files = [f for f in listdir(project_directory) if isfile(join(project_directory, f))]
	for f in files:
		os.rename(project_directory + "/" + f, archive_path + f)
	shutil.make_archive(finished_path+archive_name, "zip", root_dir=project_directory)
	finished_archive_path = finished_path + archive_name + ".zip"
	shutil.rmtree(project_directory)
	return finished_archive_path
	
if __name__ == "__main__":
    app.run()
