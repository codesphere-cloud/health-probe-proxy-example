import socket
import threading
import socketserver
import argparse

class ForwardingHandler(socketserver.BaseRequestHandler):
    def handle(self):
        # The forward_to host and port are now attached to the server instance
        forward_to_host = self.server.forward_to_host
        forward_to_port = self.server.forward_to_port
        
        try:
            # Connect to the destination
            with socket.create_connection((forward_to_host, forward_to_port)) as downstream_socket:
                print(f"New connection from {self.client_address} -> {forward_to_host}:{forward_to_port}")

                # Create threads to shuttle data in both directions
                client_to_downstream = threading.Thread(target=self.shuttle, args=(self.request, downstream_socket))
                downstream_to_client = threading.Thread(target=self.shuttle, args=(downstream_socket, self.request))

                client_to_downstream.start()
                downstream_to_client.start()

                client_to_downstream.join()
                downstream_to_client.join()

        except socket.gaierror as e:
            print(f"DNS resolution error for downstream target {forward_to_host}: {e}")
        except ConnectionRefusedError:
            print(f"Connection refused for downstream target {forward_to_host}:{forward_to_port}")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            self.request.close()
            print(f"Connection from {self.client_address} closed.")

    def shuttle(self, source_socket, destination_socket):
        try:
            while True:
                data = source_socket.recv(4096)
                if not data:
                    break
                destination_socket.sendall(data)
        except (ConnectionResetError, BrokenPipeError):
            pass # Connection closed by one of the parties
        finally:
            # Shutdown the write-end of the socket to signal the other thread
            try:
                destination_socket.shutdown(socket.SHUT_WR)
            except OSError:
                pass # Socket may already be closed


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Allow reusing address to avoid "Address already in use" errors
    allow_reuse_address = True
    def __init__(self, server_address, RequestHandlerClass, forward_to_host, forward_to_port):
        super().__init__(server_address, RequestHandlerClass)
        self.forward_to_host = forward_to_host
        self.forward_to_port = forward_to_port


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A simple TCP port forwarder.",
        formatter_class=argparse.RawTextHelpFormatter # For better formatting of the usage example
    )
    
    parser.add_argument("listen_port", type=int, help="The local port to listen on.")
    parser.add_argument("forward_host", type=str, help="The destination host/IP to forward traffic to.")
    parser.add_argument("forward_port", type=int, help="The destination port to forward traffic to.")
    
    parser.epilog = """
Examples:
  # Forward local port 3000 to localhost:8080
  python3 forwarder.py 3000 127.0.0.1 8080

  # Forward local port 8443 to an external web server
  python3 forwarder.py 8443 example.com 443
"""

    args = parser.parse_args()

    # Assign arguments to variables
    listen_port = args.listen_port
    forward_host = args.forward_host
    forward_port = args.forward_port
    
    print(f"Starting port forwarder: localhost:{listen_port} -> {forward_host}:{forward_port}")
    
    # Pass the forward_host and forward_port to the custom server constructor
    with ThreadedTCPServer(("0.0.0.0", listen_port), ForwardingHandler, forward_host, forward_port) as server:
        server.serve_forever()
