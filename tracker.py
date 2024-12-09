import socket
from traceback import print_tb
import enum
import psutil
import os
from threading import Thread
import json

# DEFAULT CONFIG TRACKER
DEFAULT_TRACKER_PORT = 42384
server_running = True

# Enum class to handle list peer requests
class PeerRequest(enum.Enum):
    APPEAR_PEER = "APPEAR_PEER"
    CLOSE_PEER = "CLOSE_PEER"
    GET_LIST_ACTIVE_PEERS = "GET_LIST_ACTIVE_PEERS"
    UPLOAD_FILE_LIST = "UPLOAD_FILE_LIST"
    GET_PEERS_FOR_FILES = "GET_PEERS_FOR_FILES"

class Tracker:
    def __init__(self, port=DEFAULT_TRACKER_PORT, host=None):
        self.port = port
        self.host = host if host else socket.gethostbyname(socket.gethostname())
        self.list_of_online_peers = []
        self.list_of_files_with_peers = {}

        # Use a cross-platform directory path
        self.tracker_dir = os.path.join(os.getcwd(), "tracker")
        if not os.path.exists(self.tracker_dir):
            try:
                os.makedirs(self.tracker_dir)
            except PermissionError:
                print("Permission denied. Falling back to home directory...")
                self.tracker_dir = os.path.join(os.path.expanduser("~"), "tracker")
                os.makedirs(self.tracker_dir, exist_ok=True)

        # Check if tracker_data.json exists inside tracker directory
        tracker_data_path = os.path.join(self.tracker_dir, "tracker_data.json")
        if not os.path.exists(tracker_data_path):
            with open(tracker_data_path, "w") as f:
                json.dump({"list_of_files_with_peers": {}}, f, indent=4)
        else:
            with open(tracker_data_path, "r") as f:
                tracker_data = json.load(f)
                self.list_of_files_with_peers = tracker_data["list_of_files_with_peers"]

    def add_peer(self, peer_ip, peer_port):
        peer_address = (peer_ip, peer_port)
        if peer_address not in self.list_of_online_peers:
            self.list_of_online_peers.append(peer_address)
            print(f"Peer {peer_address} added.")
        else:
            print(f"Peer {peer_address} already exists.")

    def remove_peer(self, peer_ip, peer_port):
        peer_address = (peer_ip, peer_port)
        if peer_address in self.list_of_online_peers:
            self.list_of_online_peers.remove(peer_address)
            print(f"Peer {peer_address} removed.")

    def list_active_peers(self):
        return self.list_of_online_peers

    def add_list_file_name(self, peer_ip, peer_port, list_file_name):
        # Notice that list_file_name is a pure string
        # Given string
        # Remove the brackets and split by commas
        cleaned_str = list_file_name.strip("[]")
        file_list = cleaned_str.split(',')
        # Remove extra spaces and quotes, then separate file names
        file_names = [file.strip(" '\"") for file in file_list]

        # doesn't store PORT because client generate random port when client restarting
        peer_address = peer_ip

        for file in file_names:
            if file not in self.list_of_files_with_peers:
                self.list_of_files_with_peers[file] = [peer_address]
                # change the list_of_files_with_peers content in tracker_data.json
                with open(os.path.join(self.tracker_dir, "tracker_data.json"), "w") as f:
                    json.dump({"list_of_files_with_peers": self.list_of_files_with_peers}, f, indent=4)
            else:
                # when the file already exists in the list_of_files_with_peers
                if peer_address not in self.list_of_files_with_peers[file]:
                    self.list_of_files_with_peers[file].append(peer_address)
                    # change the list_of_files_with_peers content in tracker_data.json
                    with open(os.path.join(self.tracker_dir, "tracker_data.json"), "w") as f:
                        json.dump({"list_of_files_with_peers": self.list_of_files_with_peers}, f, indent=4)


def thread_handle_peer_request(peer_connection, peer_addr):
    connected = True
    try:
        while connected:
            data = peer_connection.recv(1024).decode('utf-8')
            if not data:
                break
            # Process the request from PEER
            if data.startswith(PeerRequest.APPEAR_PEER.value):
                _, peer_ip, peer_port = data.split(":")
                tracker_info.add_peer(peer_ip, peer_port)
                print(f"Peer {peer_ip}:{peer_port} has connected")
                connected = False
            elif data.startswith(PeerRequest.CLOSE_PEER.value):
                _, peer_ip, peer_port = data.split(":")
                tracker_info.remove_peer(peer_ip, peer_port)
                print(f"Peer {peer_ip}:{peer_port} has disconnected")
                connected = False
            elif data.startswith(PeerRequest.GET_LIST_ACTIVE_PEERS.value):
                # Handle request for peer list
                peer_list = tracker_info.list_active_peers()
                peer_list_str = ",".join([f"{peer[0]}:{peer[1]}" for peer in peer_list])
                message = "GET_LIST_ACTIVE_PEERS:" + peer_list_str
                # from TRACKER send back list of peers to PEER
                peer_connection.send(message.encode())
                print(f"Sent peer list to {peer_addr}")
                connected = False
            elif data.startswith(PeerRequest.UPLOAD_FILE_LIST.value):
                # Split the data to handle multiple messages
                messages = data.strip().split("\n")  # Use newline as a delimiter
                for message in messages:
                    try:
                        # Parse individual messages
                        _, peer_ip, peer_port, file_name = message.split(":")
                        print(f"Peer {peer_ip}:{peer_port} has uploaded file: {file_name}")

                        # Add the file name to the tracker's list
                        tracker_info.add_list_file_name(peer_ip, peer_port, file_name)
                    except ValueError as e:
                        print(f"Error parsing message: {message} - {e}")
            elif data.startswith(PeerRequest.GET_PEERS_FOR_FILES.value):
                _, file_list_str = data.split(":")
                print(f"Peer {peer_addr} requested peers for files: {file_list_str}")

                # Remove "dict_keys([" and the trailing "])"
                cleaned_string = file_list_str.replace("dict_keys([", "").replace("])", "")

                # Split the remaining string by commas and strip quotes and whitespace
                file_list = [name.strip(" '\"") for name in cleaned_string.split(",")]

                # Dictionary to hold the result: {file_name: [(peer_ip, peer_port), ...]}
                peers_for_files = {}

                for file in file_list:
                    # Check if the file exists in the tracker_info.list_of_files_with_peers
                    if file in tracker_info.list_of_files_with_peers:
                        # Get the list of peers associated with this file
                        peers_for_file = tracker_info.list_of_files_with_peers[file]

                        # Filter peers that are online
                        online_peers = [
                            (peer_ip, peer_port)
                            for peer_ip in peers_for_file
                            for peer_port in [peer_port for peer_ip_, peer_port in tracker_info.list_of_online_peers if
                                              peer_ip_ == peer_ip]
                        ]

                        # Store the result in the dictionary
                        peers_for_files[file] = online_peers

                # Send back the list of peers for each file as a JSON string
                # Use ::: to separate the message type and the JSON data
                response_message = "GET_PEERS_FOR_FILES:::" + json.dumps(peers_for_files)
                peer_connection.send(response_message.encode())
                print(f"Sent list of peers for files to {peer_addr}")
                print(peers_for_files)
                connected = False
            else:
                print(f"Unknown request: {data}")
                connected = False
    except Exception as e:
        print(f"Error handling peer request from {peer_addr}: {e}")
    finally:
        pass
        # I've accidentally closed the connection here
        # This thread should hold the connection all the time


def start_tracker_server():
    tracker_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # using default host and port
    tracker_server.bind((socket.gethostbyname(socket.gethostname()), DEFAULT_TRACKER_PORT))
    tracker_server.listen()
    print(f"Tracker is running at {tracker_info.host}:{tracker_info.port}")
    # listening to new leechers connections

    count_connections = 0

    while True:
        # peer_connection is a new socket object usable to send and receive data on the connection
        # peer_addr is information about the ip address and port of the peer
        print("Waiting for new connections...")
        peer_connection, peer_addr = tracker_server.accept()
        print(f"Connection received from {peer_addr}")
        thread = Thread(target=thread_handle_peer_request, args=(peer_connection, peer_addr))
        thread.start()
        # thread.join()

def monitor_user_input_quit():
    """Thread function to monitor user input for quitting the tracker."""
    global server_running
    while server_running:
        user_input = input("Type 'q' or 'quit' to stop the tracker: ").strip().lower()
        if user_input in ['q', 'quit']:
            server_running = False
            break
    print("Tracker is shutting down...")



if __name__ == "__main__":
    # HOST and PORT of tracker
    HOST = socket.gethostbyname(socket.gethostname())
    PORT = DEFAULT_TRACKER_PORT
    tracker_info = Tracker(port=PORT, host=HOST)

    # Start the tracker server in a separate thread
    tracker_thread = Thread(target=start_tracker_server)
    tracker_thread.daemon = True
    tracker_thread.start()


    # Monitor user input in the main thread
    monitor_user_input_quit()

    # Wait for the tracker thread to finish before exiting
    # tracker_thread.join()
    print("Tracker has been stopped.")