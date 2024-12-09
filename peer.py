import socket
import threading
import time
import torrentManager
from threading import Thread
import os
import enum
import json
import shutil
import hashlib
from collections import defaultdict


# INITIAL CONFIG
HOST = socket.gethostbyname(socket.gethostname())
PORT = None
TRACKER_IP = None
TRACKER_PORT = None

class PeerRequest(enum.Enum):
    APPEAR_PEER = "APPEAR_PEER"
    CLOSE_PEER = "CLOSE_PEER"
    UPLOAD_FILE_LIST = "UPLOAD_FILE_LIST"
    GET_PEERS_FOR_FILES = "GET_PEERS_FOR_FILES"

class TrackerResponse(enum.Enum):
    GET_LIST_ACTIVE_PEERS = "GET_LIST_ACTIVE_PEERS"

import socket

# -- DOWNLOAD MODULE --
class Download:
    def __init__(self, peer, file_pieces_dict_download):
        self.peer = peer
        self.tracker_ip = peer.tracker_ip
        self.tracker_port = peer.tracker_port
        # key = file_name, value = list of seeder ip and port
        self.file_pieces_dict_download = file_pieces_dict_download
        self.list_file_seeders_port = None
    def get_list_file_seeders_port(self):
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (self.tracker_ip, self.tracker_port)
            peer_socket.connect(addr)
            # get all keys in the dictionary
            message = f"GET_PEERS_FOR_FILES:{self.file_pieces_dict_download.keys()}"
            peer_socket.send(message.encode())

            # Receive the list of active peers from the tracker
            data = peer_socket.recv(4096).decode('utf-8')
            print(data)
            _, seeders_string = data.split(":::")
            data = json.loads(seeders_string)

            # Convert list of lists into list of tuples for each file
            list_file_seeders_port = {
                file_name: [tuple(peer) for peer in peers]
                for file_name, peers in data.items()
            }
            print(list_file_seeders_port)
            peer_socket.close()
            self.list_file_seeders_port = list_file_seeders_port

        except socket.error as e:
            print(f"Failed to connect to tracker at {self.tracker_ip}:{self.tracker_port} - {e}")

    def check_already_downloaded(self):
        # Create a list of files to be removed
        files_to_remove = []

        # Identify files that have already been downloaded
        for file_name in self.list_file_seeders_port.keys():
            if os.path.exists(os.path.join("download", file_name)) or os.path.exists(
                    os.path.join("uploaded", file_name)):
                files_to_remove.append(file_name)

        # Remove identified files from the dictionary
        for file_name in files_to_remove:
            self.list_file_seeders_port.pop(file_name)

    def determine_download_strategy(self, seeder_ports, file_pieces):
        # Dictionary to store the result
        peer_download_strategy = defaultdict(lambda: defaultdict(list))

        for file_name, peer_list in seeder_ports.items():
            num_pieces = file_pieces[file_name]  # Total pieces for the current file
            piece_indexes = list(range(num_pieces))  # Create list of piece indexes [0, 1, ..., N-1]
            num_peers = len(peer_list)  # Number of peers for the file

            if num_peers == 1:
                # If only one peer holds the file, assign all pieces to this peer
                peer_ip, peer_port = peer_list[0]
                peer_download_strategy[(peer_ip, peer_port)][file_name] = piece_indexes
            else:
                # Distribute pieces among multiple peers
                pieces_per_peer = num_pieces // num_peers  # Base number of pieces per peer
                remainder_pieces = num_pieces % num_peers  # Remaining pieces to be distributed

                start = 0
                for i, (peer_ip, peer_port) in enumerate(peer_list):
                    # Calculate the number of pieces assigned to this peer
                    end = start + pieces_per_peer + (1 if i < remainder_pieces else 0)
                    peer_download_strategy[(peer_ip, peer_port)][file_name] = piece_indexes[start:end]
                    start = end
        return peer_download_strategy


# -- UPLOAD MODULE --
class Upload:
    def __init__(self, peer, file_list_upload):
        self.peer = peer
        self.file_list_upload = file_list_upload
        # Create a thread to handle the upload process
        thread = Thread(target=self.thread_upload_list_ips, args=(file_list_upload,))
        thread.start()
        thread.join()
    def thread_upload_list_ips(self, file_list_upload):
        try:
            peer_upload_file_list_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (self.peer.tracker_ip, self.peer.tracker_port)
            peer_upload_file_list_socket.connect(addr)
            message = f"UPLOAD_FILE_LIST:{peer.host}:{peer.port}:{file_list_upload}"
            peer_upload_file_list_socket.send(message.encode())
            # Log the message sent to the tracker
            print(message)
            peer_upload_file_list_socket.close()
        except socket.error as e:
            print(f"Failed to send file info to tracker: {e}")
            return


# -- PEER MODULE --
class Peer:
    def __init__(self, tracker_ip, tracker_port):
        self.port = None
        self.host = None
        # self.port = port
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port
        self.announce_online_to_tracker()

    def announce_online_to_tracker(self):
        """Announce this peer as online to the tracker."""
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (self.tracker_ip, self.tracker_port)
            peer_socket.connect(addr)

            # Get current peer_ip and peer_port information
            peer_ip, peer_port = peer_socket.getsockname()
            self.host = peer_ip
            self.port = peer_port

            message = f"APPEAR_PEER:{self.host}:{self.port}"
            peer_socket.send(message.encode())
            print(f"Successfully announced online to tracker at {self.tracker_ip}:{self.tracker_port}")
            peer_socket.close()
        except socket.error as e:
            print(f"Failed to connect to tracker at {self.tracker_ip}:{self.tracker_port} - {e}")
        time.sleep(3)

    def announce_offline_to_tracker(self):
        """Announce this peer as offline to the tracker."""
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (self.tracker_ip, self.tracker_port)
            peer_socket.connect(addr)
            message = f"CLOSE_PEER:{self.host}:{self.port}"
            peer_socket.send(message.encode())
            print(f"Successfully announced offline to tracker at {self.tracker_ip}:{self.tracker_port}")
            peer_socket.close()
        except socket.error as e:
            print(f"Failed to connect to tracker at {self.tracker_ip}:{self.tracker_port} - {e}")
        time.sleep(3)

    def peer_upload_file(self):
        try:
            new_torrent_file = torrentManager.CreateTorrentFile(self.tracker_ip, self.tracker_port)
            torrent_file_status = new_torrent_file.create_torrent_file()
            if torrent_file_status == True:
                list_of_files = new_torrent_file.get_list_file_names()
                upload_module = Upload(self, list_of_files)

                # After uploading, move the files from the upload directory uploaded directory
                if not os.path.exists("uploaded"):
                    os.makedirs("uploaded")

                for file in list_of_files:
                    os.rename(os.path.join("upload", file), os.path.join("uploaded", file))
                print("Successfully created torrent file. Torrent's name: ", new_torrent_file.torrent_name)

        except Exception as e:
            print(f"Error uploading files: {e}")
            return

    def peer_get_active_peers(self):
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            addr = (self.tracker_ip, self.tracker_port)
            peer_socket.connect(addr)
            message = f"GET_LIST_ACTIVE_PEERS"
            peer_socket.send(message.encode())

            # Receive the list of active peers from the tracker
            data = peer_socket.recv(1024).decode('utf-8')
            print(data)

            peer_socket.close()
        except socket.error as e:
            print(f"Failed to connect to tracker at {self.tracker_ip}:{self.tracker_port} - {e}")

    def peer_download_file(self):
        # TODO: STEP 1 - Get the list of torrent files in the directory
        torrent_path = os.path.join(os.getcwd(), "use_torrent_to_download")
        print("Torrent path: ", torrent_path)

        # Check if the directory exists
        if not os.path.exists(torrent_path):
            print(f"The directory '{torrent_path}' does not exist.")
            return
        # Get the list of all files in the directory
        try:
            file_names = [
                file_name for file_name in os.listdir(torrent_path)
                if file_name.startswith("torrent_file") and file_name.endswith(".json")
            ]
            print("Filtered files:")
            for file_name in file_names:
                print(file_name)

            torrent_file_name = file_names[0]
            torrent_file_path = os.path.join(torrent_path, torrent_file_name)
        except Exception as e:
            print(f"Error accessing the directory: {e}")
            return

        # TODO: STEP 2 - Read the torrent file, then get the file list
        open_torrent_file = torrentManager.ReadTorrentFile(torrent_file_path)
        file_pieces_dict_download = open_torrent_file.get_list_file_names()
        print("File list to download with number of pieces:", file_pieces_dict_download)

        # TODO: STEP 3 - Send the file list to the tracker
        # TODO: Also store tracker list response inside Download module
        download_module = Download(self, file_pieces_dict_download)
        download_module.get_list_file_seeders_port()

        # TODO: STEP 4 - Check if any file has already been downloaded (in folder download or uploaded)
        # This step modify the list of file to download inside the Download module
        download_module.check_already_downloaded()

        # TODO: STEP 5 - (MOST IMPORTANT STEP)
        # TODO: Define download strategy for this peer
        # Recheck the list of file to download, and number of pieces for each file
        print("*** RECHECK THE LIST OF FILE TO DOWNLOAD ***")

        # In the list of files, if a file doesn't have any seeder ip and port, remove it from the list
        download_module.list_file_seeders_port = {
            file_name: seeders
            for file_name, seeders in download_module.list_file_seeders_port.items() if seeders
        }

        print(download_module.list_file_seeders_port)
        if not download_module.list_file_seeders_port:
            print("No files to download. Exiting...")
            return

        print("*** RECHECK THE FILES AND NUMBER OF PIECES ***")
        print(file_pieces_dict_download)
        peers_strategy = download_module.determine_download_strategy(download_module.list_file_seeders_port, file_pieces_dict_download)

        # Print the download strategy
        print("*** DOWNLOAD STRATEGY ***")
        for peer, files in peers_strategy.items():
            print(f"{peer}")
            for file, pieces in files.items():
                print(f"- file '{file}' => piece {pieces}")

        # TODO: STEP 6: Download file pieces
        print("*** STARTING DOWNLOAD ***")
        for peer, files in peers_strategy.items():
            for file_name, pieces in files.items():
                for piece in pieces:
                    try:
                        print(f"Requesting pieces [{piece}] of '{file_name}' from {peer[0]}")
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as peer_socket:
                            peer_socket.connect((peer[0], 50535))
                            message = f"GET_PIECE:{file_name}:{piece}"
                            peer_socket.send(message.encode())

                            # Receive piece data
                            piece_data = peer_socket.recv(1024)
                            if not piece_data:
                                raise Exception("Empty piece data received")

                            # Save the piece to a temporary directory
                            temp_dir = os.path.join(os.getcwd(), "temp", file_name)
                            if not os.path.exists(temp_dir):
                                os.makedirs(temp_dir)

                            with open(os.path.join(temp_dir, f"piece_{piece}"), "wb") as f:
                                f.write(piece_data)
                            print(f"Downloaded piece {piece} of '{file_name}' from {peer[0]}")

                    except Exception as e:
                        print(f"Failed to connect or download from peer {peer[0]}")

        # TODO: STEP 7: Reconstruct files
        print("*** RECONSTRUCTING FILES ***")
        for file_name, num_pieces in file_pieces_dict_download.items():
            temp_dir = os.path.join(os.getcwd(), "temp", file_name)
            try:
                with open(os.path.join("download", file_name), "wb") as output_file:
                    for piece_index in range(num_pieces):
                        piece_path = os.path.join(temp_dir, f"piece_{piece_index}")
                        if os.path.exists(piece_path):
                            with open(piece_path, "rb") as piece_file:
                                output_file.write(piece_file.read())
                        else:
                            print(f"Piece {piece_index} of '{file_name}' is missing. File reconstruction incomplete.")
                            break
                    else:
                        print(f"Successfully reconstructed file: '{file_name}'")
            except Exception as e:
                print(f"Error reconstructing file '{file_name}': {e}")
            finally:
                # Ensure the temp directory is removed, even if reconstruction fails
                if os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                        print(f"Temporary folder '{temp_dir}' deleted.")
                    except Exception as delete_error:
                        print(f"Error deleting temporary folder '{temp_dir}': {delete_error}")


        # TODO: Step 8 - Notify the tracker that the download is complete and the peer is now a seeder for the file
        peer_upload_file_list_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = (self.tracker_ip, self.tracker_port)
        peer_upload_file_list_socket.connect(addr)

        for file_name in file_pieces_dict_download.keys():
            message = f"{PeerRequest.UPLOAD_FILE_LIST.value}:{self.host}:{self.port}:{file_name}\n"
            peer_upload_file_list_socket.send(message.encode())
            print(f"Sent: {message.strip()}")  # Log each message



def thread_handle_peer_download_request():
    peer_download_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    peer_download_server.bind((HOST, 50535))
    peer_download_server.listen()
    print(f"Peer download server is running at {HOST}:50535")

    while True:
        peer_download_connection, peer_download_addr = peer_download_server.accept()
        print(f"Download connection received from {peer_download_addr}")

        # Spawn a new thread for each request
        threading.Thread(
            target=handle_request,
            args=(peer_download_connection, peer_download_addr),
        ).start()

def handle_request(peer_download_connection, peer_download_addr):
    try:
        data = peer_download_connection.recv(1024).decode('utf-8')
        if not data:
            return

        print(f"Received request: {data}")
        if data.startswith("GET_PIECE"):
            _, file_name, piece_index = data.split(":")
            piece_index = int(piece_index)

            # Locate and send the requested piece
            file_path = os.path.join("uploaded", file_name)
            if not os.path.exists(file_path):
                # try to find the file in the download directory
                file_path = os.path.join("download", file_name)
                if not os.path.exists(file_path):
                    peer_download_connection.send(f"ERROR: File '{file_name}' not found.".encode())
                    return

            piece_size = 512
            file_size = os.path.getsize(file_path)
            start_offset = piece_index * piece_size
            end_offset = min(start_offset + piece_size, file_size)

            if start_offset >= file_size:
                peer_download_connection.send(f"ERROR: Invalid piece index {piece_index}.".encode())
                return

            with open(file_path, "rb") as file:
                file.seek(start_offset)
                piece_data = file.read(end_offset - start_offset)

            peer_download_connection.send(piece_data)
            print(f"Sent piece {piece_index} of '{file_name}' to {peer_download_addr}")

    except Exception as e:
        print(f"Error handling peer request: {e}")
    finally:
        peer_download_connection.close()



# --- MAIN PROGRAM ---
if __name__ == "__main__":
    TRACKER_IP = input("Please type the Tracker IP: ")

    TRACKER_PORT = 42384

    # Store the peer's information
    # This code also announce the peer to the tracker
    peer = Peer(TRACKER_IP, TRACKER_PORT)

    # Start the thread to handle download requests from other peers
    thread_download = Thread(target=thread_handle_peer_download_request)
    thread_download.daemon = True
    thread_download.start()

    print("Peer is running at: ", peer.host, ":", peer.port)

    while True:
        print("\nMenu:")
        print("1. Upload files and create torrent file")
        print("2. Download file")
        print("3. Show all active peers")
        print("4. Exit")

        choice = input("Choose an option: ")

        if choice == "1":
            peer.peer_upload_file()
        elif choice == "2":
            peer.peer_download_file()
        elif choice == "3":
            peer.peer_get_active_peers()
            pass
        elif choice == "4":
            print("Peer goes offline, peer shutting down.")
            peer.announce_offline_to_tracker()
            time.sleep(1)
            exit()  # Exit the program
        else:
            print("Invalid choice. Please choose again.")