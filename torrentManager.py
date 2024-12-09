import os
import hashlib
import json
import json
import hashlib
import random
import string

import locale
import sys

class CreateTorrentFile:
    def __init__(self, tracker_ip, tracker_port, piece_size=512):
        # Define upload and torrent directories
        self.upload_dir = os.path.join(os.getcwd(), "upload")
        self.torrent_dir = os.path.join(os.getcwd(), "torrent")
        # Ensure the directories exist
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
        if not os.path.exists(self.torrent_dir):
            os.makedirs(self.torrent_dir)
        self.piece_size = piece_size
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port
        self.list_file_names = [f for f in os.listdir(self.upload_dir) if os.path.isfile(os.path.join(self.upload_dir, f))]
        self.torrent_name = "torrent_file" + self.generate_random_string(5) + ".json"

    def generate_random_string(self, length):
        # Define the pool of characters: uppercase letters and digits
        characters = string.ascii_uppercase + string.digits
        # Use random.choice to select random characters from the pool
        random_string = ''.join(random.choice(characters) for _ in range(length))
        return random_string
    def create_torrent_file(self):
        piece_size = 512  # Default piece size in bytes

        # Ensure the upload directory exists
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)

        # Get all files name in the upload directory

        if not self.list_file_names:
            print("No files found in the upload directory.")
            return False

        # Ensure the torrent directory exists
        if not os.path.exists(self.torrent_dir):
            os.makedirs(self.torrent_dir)

        # Prepare the torrent file data
        torrent_data = {
            "tracker_ip": self.tracker_ip,
            "tracker_port": self.tracker_port,
            "num_files": len(self.list_file_names),
            "files": []
        }

        for file_name in self.list_file_names:
            file_dir = os.path.join(self.upload_dir, file_name)

            if os.path.exists(file_dir):
                print(f"Processing file: {file_name}")

                # Get file information
                file_size = os.path.getsize(file_dir)
                file_extension = os.path.splitext(file_name)[1]
                num_pieces = (file_size + piece_size - 1) // piece_size  # Calculate number of pieces

                # Calculate SHA-1 hashes for each piece
                piece_hashes = []
                with open(file_dir, "rb") as file:
                    while chunk := file.read(piece_size):
                        sha1 = hashlib.sha1(chunk).hexdigest()
                        piece_hashes.append(sha1)

                # Add file information to torrent data
                torrent_data["files"].append({
                    "file_name": file_name,
                    "file_extension": file_extension,
                    "file_size": file_size,
                    "piece_size": piece_size,
                    "num_pieces": num_pieces,
                    "piece_hashes": piece_hashes
                })
            else:
                print(f"File does not exist: {file_dir}")
                return False

        # Save the torrent data as a JSON file
        torrent_file_name = self.torrent_name
        torrent_file_path = os.path.join(self.torrent_dir, torrent_file_name)
        with open(torrent_file_path, "w") as torrent_file:
            json.dump(torrent_data, torrent_file, indent=4)

        print(f"Torrent file created successfully: {torrent_file_path}")
        return True
    def get_list_file_names(self):
        return self.list_file_names


class ReadTorrentFile:
    def __init__(self, torrent_file_path):
        self.torrent_file_path = torrent_file_path
        self.torrent_data = None
    def get_list_file_names(self):
        peer_get_file_list = []
        try:
            with open(self.torrent_file_path, "r") as torrent_file:
                torrent_data = json.load(torrent_file)
            file_names = [file["file_name"] for file in torrent_data["files"]]
            pieces = [file["num_pieces"] for file in torrent_data["files"]]

            # Combine the two lists into a dictionary
            files_pieces_dict = dict(zip(file_names, pieces))
            return files_pieces_dict
        except Exception as e:
            print(f"Error reading the torrent file: {e}")
            return