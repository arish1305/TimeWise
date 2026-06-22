import socket

gateways = [f"172.{sub}.0.1" for sub in range(17, 23)]
ports = [5432, 5435]

for ip in gateways:
    for port in ports:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((ip, port))
            print(f"Port {port} is OPEN on gateway {ip}!")
        except Exception:
            pass
        finally:
            s.close()
