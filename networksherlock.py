import sys
import time
import socket
import argparse
import threading
import ipaddress
import subprocess
from rich import print
from queue import Queue

class PortScanner:
    def __init__(self, targets, ports, threads=10, protocol='tcp', version_info=False, save_results=None, ping_check=False):
        self.targets = targets
        self.ports = ports
        self.threads = threads
        self.protocol = protocol
        self.version_info = version_info
        self.save_results = save_results
        self.ping_check = ping_check
        self.ip = None

    def format_scan_time(self, seconds):
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)} minute {seconds:.2f} seconds"

    def banner_grabbing(self, ip, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((ip, port))
            if port == 80 or port == 443:
                sock.send(b"HEAD / HTTP/1.1\r\nHost: " + ip.encode() + b"\r\n\r\n")
            elif port == 21:
                sock.send(b"USER anonymous\r\n")
            elif port == 22:
                sock.send(b"SSH-2.0-OpenSSH_7.3\r\n")
            elif port == 25:
                sock.send(b"HELO " + ip.encode() + b"\r\n")
            elif port == 23:
                sock.send(b"\xFF\xFD\x18\xFF\xFD\x20\xFF\xFD\x23\xFF\xFD\x27\xFF\xFA\x1F\x00\x50\x00\x18\xFF\xF0")
            elif port == 3306:
                sock.send(b"\x05\x00\x00\x01\x85\xa6\x03\x00\x00\x00\x00\x21\x00\x00\x00\x02\x3f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
            elif port == 139 or port == 445:
                sock.send(b"\x00\x00\x00\x85\xff\x53\x4d\x42\x72\x00\x00\x00\x00\x18\x53\xc8\x17\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x2f\x4b\x00\x00\x00\x00\x00\x31\x00\x02\x50\x43\x20\x4e\x45\x54\x57\x4f\x52\x4b\x20\x50\x52\x4f\x47\x52\x41\x4d\x20\x31\x2e\x30\x00\x02\x4c\x41\x4e\x4d\x41\x4e\x31\x2e\x30\x00\x02\x57\x69\x6e\x64\x6f\x77\x73\x20\x66\x6f\x72\x20\x57\x6f\x72\x6b\x67\x72\x6f\x75\x70\x73\x20\x33\x2e\x31\x61\x00\x02\x4c\x4d\x31\x2e\x32\x58\x30\x30\x32\x00\x02\x4c\x41\x4e\x4d\x41\x4e\x32\x2e\x31\x00\x02\x4e\x54\x20\x4c\x4d\x20\x30\x2e\x31\x32\x00")
            banner = sock.recv(1024).decode("utf-8", errors="ignore").strip()
            return banner.split("\n")[0]
        except Exception as e:
            return ""

    def port_scan(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM if self.protocol == 'tcp' else socket.SOCK_DGRAM)
        sock.settimeout(1)
        result = sock.connect_ex((self.ip, port))
        if result == 0:
            try:
                service = socket.getservbyport(port, self.protocol)
            except OSError:
                service = "unknown"
            banner = ""
            if self.version_info:
                banner = self.banner_grabbing(self.ip, port)
            port_info = f"{port:<4}/{self.protocol}     open     {service:<14} {banner}"
            self.open_ports.append(port_info)
        sock.close()

    def ping_check(self):
        command = ["ping", "-c", "1", self.ip]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0

    def thread_process(self):
        while True:
            port = self.port_queue.get()
            if port is None:
                break
            self.port_scan(port)
            self.port_queue.task_done()

    def parse_targets(self, targets):
        parsed_targets = []
        for target in targets.split(','):
            if '/' in target or '-' in target:
                if '-' in target:
                    start_ip, end_ip = target.split('-')
                    start_ip = ipaddress.ip_address(start_ip)
                    end_ip = ipaddress.ip_address(end_ip)
                    while start_ip <= end_ip:
                        parsed_targets.append(str(start_ip))
                        start_ip += 1
                else:  # CIDR Notation
                    for ip in ipaddress.ip_network(target, strict=False):
                        parsed_targets.append(str(ip))
            else:
                parsed_targets.append(target.strip())
        return parsed_targets

    def scan(self):
        targets = self.parse_targets(self.targets)
        for target in targets:
            self.ip = target
            self.open_ports = []

            if self.ping_check and not self.ping_check():
                continue  # Eğer ping başarısızsa, sonraki hedefe geç

            # Port listesi oluştur
            if "-" in self.ports:
                start_port, end_port = map(int, self.ports.split('-'))
                ports = range(start_port, end_port + 1)
            elif "," in self.ports:
                ports = map(int, self.ports.split(','))
            elif self.ports.isdigit():
                ports = [int(self.ports)]
            else:
                print("[red]Invalid port format.[/red]")
                continue

            # Thread'leri başlat
            self.port_queue = Queue()
            for port in ports:
                self.port_queue.put(port)

            threads = []
            for _ in range(self.threads):
                t = threading.Thread(target=self.thread_process)
                t.start()
                threads.append(t)

            for _ in range(self.threads):
                self.port_queue.put(None)

            for t in threads:
                t.join()

            # Açık portları yazdır
            if self.open_ports:
                print(f"********************************************")
                print(f"Scanning target: {target}")
                print(f"Scanning IP    : {self.ip}")
                print(f"Ports          : {self.ports}")
                print(f"Threads        : {self.threads}")
                print(f"Protocol       : {self.protocol}")
                print(f"---------------------------------------------")
                if self.version_info:
                    print(f"[red]Port        Status   Service           VERSION[/red]")
                else:
                    print(f"[red]Port        Status   Service[/red]")
            for port_info in self.open_ports:
                print(port_info)
        print(f"---------------------------------------------")


# Ana program akışı
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='NetworkSherlock: Port Scan Tool')
    parser.add_argument('target', type=str, help='Target IP address(es), range, or CIDR (e.g., 192.168.1.1, 192.168.1.1-192.168.1.5, 192.168.1.0/24)')
    parser.add_argument('-p', '--ports', type=str, default='1-1000', help='Ports to scan (e.g. 1-1024, 21,22,80, or 80)')
    parser.add_argument('-t', '--threads', type=int, default=10, help='Number of threads to use')
    parser.add_argument('-P', '--protocol', type=str, default='tcp', choices=['tcp', 'udp'], help='Protocol to use for scanning')
    parser.add_argument('-V', '--version-info', action='store_true', help='Used to get version information')
    parser.add_argument('-s', '--save-results', type=str, help='File to save scan results')
    parser.add_argument('-c', '--ping-check', action='store_true', help='Perform ping check before scanning')
    args = parser.parse_args()

    scanner = PortScanner(args.target, args.ports, args.threads, args.protocol, args.version_info, args.save_results, args.ping_check)
    scanner.scan()